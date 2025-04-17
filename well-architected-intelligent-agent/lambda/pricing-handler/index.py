import boto3
import json
import re
import uuid
import os
import time
import logging
from botocore.exceptions import ClientError
from urllib.parse import unquote_plus
from decimal import Decimal
import itertools
import botocore.session

# Configure logging
logger = logging.getLogger()
logger.setLevel(logging.INFO)

# Configuration parameters
OUTPUT_BUCKET = os.environ.get('OUTPUT_BUCKET', 'my-output-bucket')
OUTPUT_PREFIX = os.environ.get('OUTPUT_PREFIX', '')  # New parameter for prefix
BEDROCK_MODEL_ID = os.environ.get('BEDROCK_MODEL_ID', 'anthropic.claude-v2.1')
MAX_RETRIES = int(os.environ.get('MAX_RETRIES', '3'))
RETRY_DELAY = int(os.environ.get('RETRY_DELAY', '2'))
PRICING_CACHE_TTL = int(os.environ.get('PRICING_CACHE_TTL', '86400'))  # 24 hours in seconds

# Initialize AWS clients
textract = boto3.client('textract')
bedrock = boto3.client('bedrock-runtime')
s3 = boto3.client('s3')
pricing = boto3.client('pricing')
dynamodb = boto3.resource('dynamodb')
service_quotas = boto3.client('service-quotas')  # New client for service quotas

# Enhanced regex for AWS service detection (kept for backward compatibility)
SERVICE_REGEX = r'\b(EC2|S3|RDS|Lambda|DynamoDB|ECS|EKS|SQS|SNS|CloudFront|API Gateway|Route53|CloudWatch|IAM|VPC|ELB|ALB|NLB|CloudFormation|Step Functions|Kinesis|Glue|Athena|EMR|Redshift|ElastiCache|Neptune|DocumentDB|MSK|OpenSearch|Elasticsearch|CodePipeline|CodeBuild|CodeDeploy|CodeCommit|Amplify|AppSync|EventBridge|CloudTrail|GuardDuty|WAF|Shield|Secrets Manager|KMS|ACM|Cognito|SES|Pinpoint)\b'

# Original service mappings (kept for backward compatibility)
ORIGINAL_SERVICE_MAPPING = {
    "ec2": "AmazonEC2",
    "s3": "AmazonS3",
    "rds": "AmazonRDS",
    "lambda": "AWSLambda",
    "dynamodb": "AmazonDynamoDB",
    "ecs": "AmazonECS",
    "eks": "AmazonEKS",
    "sqs": "AmazonSQS",
    "sns": "AmazonSNS",
    "cloudfront": "AmazonCloudFront",
    "api gateway": "AmazonApiGateway",
    "apigateway": "AmazonApiGateway",
    "route53": "AmazonRoute53",
    "cloudwatch": "AmazonCloudWatch",
    "iam": "AWSIdentityAndAccessManagement",
    "vpc": "AmazonVPC",
    "elb": "AmazonElasticLoadBalancing",
    "alb": "AmazonElasticLoadBalancing",
    "nlb": "AmazonElasticLoadBalancing",
    "cloudformation": "AWSCloudFormation",
    "step functions": "AWSStepFunctions",
    "kinesis": "AmazonKinesis",
    "glue": "AWSGlue",
    "athena": "AmazonAthena",
    "emr": "AmazonEMR",
    "redshift": "AmazonRedshift",
    "elasticache": "AmazonElastiCache",
    "neptune": "AmazonNeptune",
    "documentdb": "AmazonDocumentDB",
    "msk": "AmazonMSK",
    "opensearch": "AmazonOpenSearch",
    "elasticsearch": "AmazonES",
    "codepipeline": "AWSCodePipeline",
    "codebuild": "AWSCodeBuild",
    "codedeploy": "AWSCodeDeploy",
    "codecommit": "AWSCodeCommit",
    "amplify": "AWSAmplify",
    "appsync": "AWSAppSync",
    "eventbridge": "AmazonEventBridge",
    "cloudtrail": "AWSCloudTrail",
    "guardduty": "AWSGuardDuty",
    "waf": "AWSWAF",
    "shield": "AWSShield",
    "secrets manager": "AWSSecretsManager",
    "kms": "AWSKMS",
    "acm": "AWSCertificateManager",
    "cognito": "AmazonCognito",
    "ses": "AmazonSES",
    "pinpoint": "AmazonPinpoint"
}

# Original quota service mappings (kept for backward compatibility)
ORIGINAL_QUOTA_SERVICE_MAPPING = {
    "ec2": "ec2",
    "s3": "s3",
    "rds": "rds",
    "lambda": "lambda",
    "dynamodb": "dynamodb",
    "ecs": "ecs",
    "eks": "eks",
    "sqs": "sqs",
    "sns": "sns",
    "cloudfront": "cloudfront",
    "api gateway": "apigateway",
    "route53": "route53",
    "cloudwatch": "cloudwatch",
    "iam": "iam",
    "vpc": "vpc",
    "elb": "elasticloadbalancing",
    "alb": "elasticloadbalancing",
    "nlb": "elasticloadbalancing",
    "cloudformation": "cloudformation",
    "step functions": "states",
    "kinesis": "kinesis",
    "glue": "glue",
    "athena": "athena",
    "emr": "elasticmapreduce",
    "redshift": "redshift",
    "elasticache": "elasticache",
    "neptune": "neptune",
    "documentdb": "docdb",
    "msk": "kafka",
    "opensearch": "es",
    "elasticsearch": "es",
    "codepipeline": "codepipeline",
    "codebuild": "codebuild",
    "codedeploy": "codedeploy",
    "codecommit": "codecommit",
    "amplify": "amplify",
    "appsync": "appsync",
    "eventbridge": "events",
    "cloudtrail": "cloudtrail",
    "guardduty": "guardduty",
    "waf": "waf",
    "shield": "shield",
    "secrets manager": "secretsmanager",
    "kms": "kms",
    "acm": "acm",
    "cognito": "cognito-idp",
    "ses": "ses",
    "pinpoint": "pinpoint"
}

# Initialize dynamic service mappings
SERVICE_MAPPING = {}
QUOTA_SERVICE_MAPPING = {}
AVAILABLE_PRICING_SERVICES = {}
AVAILABLE_QUOTA_SERVICES = {}

def get_all_aws_services():
    """
    Dynamically retrieve all available AWS services using the boto3 session
    """
    session = botocore.session.get_session()
    available_services = session.get_available_services()
    return available_services

def build_service_mappings():
    """
    Dynamically build service mappings for pricing and quotas
    """
    available_services = get_all_aws_services()
    
    # Build pricing service mapping
    pricing_mapping = {}
    for service in available_services:
        # Convert service name to likely pricing API name
        # Most services follow a pattern like 'dynamodb' -> 'AmazonDynamoDB'
        if service.startswith('amazon-'):
            service_name = service[7:]  # Remove 'amazon-' prefix
            pricing_name = f"Amazon{service_name.title().replace('-', '')}"
        elif service.startswith('aws-'):
            service_name = service[4:]  # Remove 'aws-' prefix
            pricing_name = f"AWS{service_name.title().replace('-', '')}"
        else:
            # Handle common prefixes
            if service in ['s3', 'ec2', 'rds', 'sns', 'sqs', 'efs']:
                pricing_name = f"Amazon{service.upper()}"
            else:
                pricing_name = f"Amazon{service.title().replace('-', '')}"
        
        pricing_mapping[service] = pricing_name
        # Also add common variations
        pricing_mapping[service.replace('-', '')] = pricing_name
        pricing_mapping[service.replace('-', ' ')] = pricing_name
    
    # Add manual overrides for special cases, including all original mappings
    pricing_mapping.update(ORIGINAL_SERVICE_MAPPING)
    
    # Build service quotas mapping
    quotas_mapping = {}
    for service in available_services:
        # For quotas, we typically use the service name directly
        quotas_mapping[service] = service
        quotas_mapping[service.replace('-', '')] = service
        quotas_mapping[service.replace('-', ' ')] = service
    
    # Add manual overrides for special cases, including all original mappings
    quotas_mapping.update(ORIGINAL_QUOTA_SERVICE_MAPPING)
    
    return pricing_mapping, quotas_mapping

def get_available_pricing_services():
    """
    Get a list of services available in the AWS Pricing API
    """
    try:
        response = pricing.describe_services()
        services = response.get('Services', [])
        
        # Extract service codes and create a mapping
        service_codes = {}
        for service in services:
            code = service.get('ServiceCode')
            if code:
                service_codes[code] = {
                    'attributes': [attr.get('Name') for attr in service.get('AttributeNames', [])]
                }
        
        return service_codes
    except Exception as e:
        logger.warning(f"Error getting available pricing services: {str(e)}")
        return {}

def get_available_service_quotas_services():
    """
    Get a list of services available in the AWS Service Quotas API
    """
    try:
        service_quotas_client = boto3.client('service-quotas')
        services = []
        paginator = service_quotas_client.get_paginator('list_services')
        
        for page in paginator.paginate():
            services.extend(page.get('Services', []))
        
        # Extract service codes
        service_codes = {service.get('ServiceCode'): service.get('ServiceName') for service in services}
        return service_codes
    except Exception as e:
        logger.warning(f"Error getting available service quotas services: {str(e)}")
        return {}

def extract_services_from_diagram(analysis_result):
    """
    Extract AWS service names from architecture diagrams by looking for common patterns
    """
    services = set()
    
    # Look for architecture diagram descriptions
    diagram_patterns = [
        r'Architecture diagram shows ([^.]+)',
        r'The diagram includes ([^.]+)',
        r'The architecture consists of ([^.]+)',
        r'The system uses ([^.]+)',
        r'The infrastructure includes ([^.]+)'
    ]
    
    for pattern in diagram_patterns:
        matches = re.finditer(pattern, analysis_result, re.IGNORECASE)
        for match in matches:
            description = match.group(1).lower()
            
            # Look for AWS service names in the description
            for service in get_all_aws_services():
                service_name = service.lower()
                if service_name in description:
                    services.add(service_name)
                
                # Check variations
                variations = [
                    service_name.replace('-', ''),
                    service_name.replace('-', ' ')
                ]
                
                for variation in variations:
                    if variation in description:
                        services.add(service_name)
    
    return list(services)

def ensure_pricing_cache_table_exists():
    """
    Ensure the pricing cache DynamoDB table exists, creating it if necessary
    """
    table_name = os.environ.get('PRICING_CACHE_TABLE', 'PricingCache')
    
    try:
        # Check if table exists
        dynamodb.meta.client.describe_table(TableName=table_name)
        logger.info(f"DynamoDB table {table_name} already exists")
        return dynamodb.Table(table_name)
    except ClientError as e:
        if e.response['Error']['Code'] == 'ResourceNotFoundException':
            logger.info(f"Creating DynamoDB table {table_name}")
            
            # Create the table
            table = dynamodb.create_table(
                TableName=table_name,
                KeySchema=[
                    {
                        'AttributeName': 'cache_key',
                        'KeyType': 'HASH'  # Partition key
                    }
                ],
                AttributeDefinitions=[
                    {
                        'AttributeName': 'cache_key',
                        'AttributeType': 'S'  # String
                    }
                ],
                BillingMode='PAY_PER_REQUEST'  # On-demand capacity
            )
            
            # Wait for table to be created
            table.meta.client.get_waiter('table_exists').wait(TableName=table_name)
            logger.info(f"DynamoDB table {table_name} created successfully")
            return table
        else:
            logger.error(f"Error checking DynamoDB table: {str(e)}")
            raise

# Initialize the pricing cache table
try:
    pricing_cache_table = ensure_pricing_cache_table_exists()
except Exception as e:
    logger.warning(f"Could not initialize pricing cache table: {str(e)}")
    pricing_cache_table = None

def lambda_handler(event, context):
    """
    Main Lambda handler function that processes S3 events
    """
    try:
        # Initialize service mappings if not already done
        global SERVICE_MAPPING, QUOTA_SERVICE_MAPPING, AVAILABLE_PRICING_SERVICES, AVAILABLE_QUOTA_SERVICES
        if not SERVICE_MAPPING or not QUOTA_SERVICE_MAPPING:
            SERVICE_MAPPING, QUOTA_SERVICE_MAPPING = build_service_mappings()
        
        # Initialize available services if not already done
        if not AVAILABLE_PRICING_SERVICES:
            try:
                AVAILABLE_PRICING_SERVICES = get_available_pricing_services()
            except Exception as e:
                logger.warning(f"Could not initialize pricing services: {str(e)}")
                AVAILABLE_PRICING_SERVICES = {}
        
        if not AVAILABLE_QUOTA_SERVICES:
            try:
                AVAILABLE_QUOTA_SERVICES = get_available_service_quotas_services()
            except Exception as e:
                logger.warning(f"Could not initialize quota services: {str(e)}")
                AVAILABLE_QUOTA_SERVICES = {}
        
        # Ensure required resources exist
        ensure_output_bucket_exists()
        
        # Extract S3 information from the event
        s3_bucket, s3_key = extract_s3_info(event)
        logger.info(f"Processing file: s3://{s3_bucket}/{s3_key}")
        
        # Step 1: Extract infrastructure text
        infrastructure_text = extract_text(s3_bucket, s3_key)
        
        # Step 2: Analyze infrastructure
        analysis_prompt = build_analysis_prompt(infrastructure_text) 
        analysis_result = query_bedrock_with_retry(analysis_prompt)
        
        # Step 3: Identify services
        services = get_services_from_analysis(analysis_result)
        logger.info(f"Identified services: {services}")
        
        # Step 4: Get pricing information
        pricing_data = {}
        for service in services:
            service_code = map_service_to_code(service)
            if service_code:
                resource_config = get_resource_config(service, analysis_result)
                filters = build_pricing_filters(service_code, resource_config)
                pricing_data[service] = get_pricing_with_cache(filters)
        
        # Step 5: Get service quotas information
        service_quotas_data = get_service_quotas(services)
        logger.info(f"Retrieved quotas for {len(service_quotas_data)} services")
        
        # Step 6: Generate cost estimation
        cost_estimate = estimate_total_costs(pricing_data, analysis_result)
        
        # Step 7: Generate recommendations with cost and quota information
        recommendations_prompt = build_recommendations_prompt(analysis_result, pricing_data, cost_estimate, service_quotas_data)
        recommendations = query_bedrock_with_retry(recommendations_prompt)
        
        # Step 8: Store output
        output = {
            "source": f"s3://{s3_bucket}/{s3_key}",
            "analysis": analysis_result,
            "services": services,
            "pricing": pricing_data,
            "service_quotas": service_quotas_data,
            "cost_estimate": cost_estimate,
            "recommendations": recommendations,
            "timestamp": time.time()
        }
        output_location = store_output(output)
        
        return {
            "statusCode": 200,
            "body": json.dumps({
                "message": "Analysis complete",
                "output_location": output_location,
                "estimated_monthly_cost": cost_estimate["total_estimated_monthly_cost"],
                "services_detected": len(services),
                "quotas_provided": len(service_quotas_data)
            })
        }
    except Exception as e:
        logger.error(f"Error processing document: {str(e)}", exc_info=True)
        return {
            "statusCode": 500,
            "body": json.dumps({
                "error": str(e)
            })
        }

def extract_s3_info(event):
    """
    Extract S3 bucket and key information from the event
    """
    # For direct invocation
    if 'bucket' in event and 'key' in event:
        return event['bucket'], unquote_plus(event['key'])
    # For S3 event notification
    elif 'Records' in event and len(event['Records']) > 0:
        s3_info = event['Records'][0]['s3']
        return s3_info['bucket']['name'], unquote_plus(s3_info['object']['key'])
    else:
        raise ValueError("Invalid event structure. Expected S3 event or direct invocation with bucket and key.")

def extract_text(s3_bucket, s3_key):
    """
    Extract text from a document in S3 using Textract for PDFs or direct reading for text files
    """
    try:
        if s3_key.lower().endswith(('.pdf', '.png', '.jpg', '.jpeg', '.tiff')):
            logger.info(f"Processing document with Textract: {s3_key}")
            return extract_text_with_textract(s3_bucket, s3_key)
        else:
            logger.info(f"Processing text document directly: {s3_key}")
            return extract_text_from_file(s3_bucket, s3_key)
    except ClientError as e:
        logger.error(f"Error extracting text: {str(e)}")
        raise

def extract_text_with_textract(s3_bucket, s3_key):
    """
    Extract text from image or PDF using Textract with pagination support
    """
    try:
        # Start document text detection for multi-page documents
        if s3_key.lower().endswith('.pdf'):
            response = textract.start_document_text_detection(
                DocumentLocation={'S3Object': {'Bucket': s3_bucket, 'Name': s3_key}}
            )
            job_id = response['JobId']
            
            # Wait for the job to complete
            status = 'IN_PROGRESS'
            while status == 'IN_PROGRESS':
                time.sleep(5)
                response = textract.get_document_text_detection(JobId=job_id)
                status = response['JobStatus']
                
            if status != 'SUCCEEDED':
                raise Exception(f"Textract job failed with status: {status}")
                
            # Get all pages
            pages = []
            next_token = None
            
            while True:
                if next_token:
                    response = textract.get_document_text_detection(JobId=job_id, NextToken=next_token)
                else:
                    response = textract.get_document_text_detection(JobId=job_id)
                
                pages.extend(response['Blocks'])
                
                if 'NextToken' in response:
                    next_token = response['NextToken']
                else:
                    break
                    
            return get_text_from_textract_blocks(pages)
        else:
            # For single-page images
            response = textract.detect_document_text(
                Document={'S3Object': {'Bucket': s3_bucket, 'Name': s3_key}}
            )
            return get_text_from_textract_blocks(response['Blocks'])
    except Exception as e:
        logger.error(f"Error in Textract processing: {str(e)}", exc_info=True)
        raise

def extract_text_from_file(s3_bucket, s3_key):
    """
    Extract text from a text file in S3
    """
    try:
        obj = s3.get_object(Bucket=s3_bucket, Key=s3_key)
        content = obj['Body'].read()
        
        # Try different encodings
        encodings = ['utf-8', 'latin-1', 'cp1252', 'iso-8859-1']
        for encoding in encodings:
            try:
                return content.decode(encoding)
            except UnicodeDecodeError:
                continue
                
        # If all encodings fail, use latin-1 as a fallback
        return content.decode('latin-1', errors='replace')
    except Exception as e:
        logger.error(f"Error reading file: {str(e)}", exc_info=True)
        raise

def get_text_from_textract_blocks(blocks):
    """
    Extract text from Textract blocks
    """
    text = ""
    for block in blocks:
        if block['BlockType'] == 'LINE' and 'Text' in block:
            text += block['Text'] + " "
    return text

def build_analysis_prompt(infrastructure_text):
    """
    Build a prompt for Bedrock to analyze infrastructure text
    """
    # Limit text length to avoid token limits
    max_text_length = 15000
    if len(infrastructure_text) > max_text_length:
        infrastructure_text = infrastructure_text[:max_text_length] + "..."
    
    prompt = {
        "anthropic_version": "bedrock-2023-05-31",
        "max_tokens": 1500,
        "messages": [
            {
                "role": "user",
                "content": f"""Analyze this infrastructure description and extract the following information:
1. AWS services mentioned
2. Resource types and configurations (include instance types, storage sizes, etc.)
3. Architecture patterns and relationships between services
4. Potential cost drivers and high-cost components
5. Security considerations

Infrastructure description:
{infrastructure_text}

Please format your response in clear sections for each category. Be specific about resource configurations when they are mentioned."""
            }
        ]
    }
    return prompt

def get_services_from_analysis(analysis_result):
    """
    Extract AWS services from the analysis result using multiple methods
    """
    services = set()
    
    # Method 1: Use regex pattern matching with all available AWS services
    available_services = get_all_aws_services()
    service_patterns = []
    
    for service in available_services:
        # Add the service name as is
        service_patterns.append(re.escape(service))
        
        # Add without hyphens
        if '-' in service:
            service_patterns.append(re.escape(service.replace('-', '')))
            service_patterns.append(re.escape(service.replace('-', ' ')))
    
    # Add common service abbreviations
    common_abbreviations = {
        "ec2": "elastic compute cloud",
        "s3": "simple storage service",
        "rds": "relational database service",
        "elb": "elastic load balancer",
        "alb": "application load balancer",
        "nlb": "network load balancer",
        "sns": "simple notification service",
        "sqs": "simple queue service",
        "iam": "identity and access management",
        "vpc": "virtual private cloud",
        "eks": "elastic kubernetes service",
        "ecs": "elastic container service",
        "msk": "managed streaming for kafka",
        "emr": "elastic mapreduce",
        "ebs": "elastic block store",
        "efs": "elastic file system",
        "waf": "web application firewall",
        "acm": "certificate manager",
        "ses": "simple email service",
        "kms": "key management service"
    }
    
    for abbr, full_name in common_abbreviations.items():
        service_patterns.append(re.escape(abbr))
        service_patterns.append(re.escape(full_name))
    
    # Create the regex pattern if we have patterns
    if service_patterns:
        try:
            service_regex = r'\b(' + '|'.join(service_patterns) + r')\b'
            
            # Find all matches
            matches = re.finditer(service_regex, analysis_result, re.IGNORECASE)
            for match in matches:
                service = match.group(1).lower()
                services.add(service)
        except Exception as e:
            logger.warning(f"Error in regex pattern matching: {str(e)}")
    
    # Method 2: Check for AWS service prefixes
    aws_prefixes = [
        r'\bAWS\s+([A-Za-z0-9\s]+)',
        r'\bAmazon\s+([A-Za-z0-9\s]+)'
    ]
    
    for prefix_pattern in aws_prefixes:
        prefix_matches = re.finditer(prefix_pattern, analysis_result)
        for match in prefix_matches:
            service_name = match.group(1).strip().lower()
            services.add(service_name)
    
    # Method 3: Extract from architecture diagram descriptions
    diagram_services = extract_services_from_diagram(analysis_result)
    services.update(diagram_services)
    
    # Method 4: Use the original SERVICE_REGEX as a fallback
    original_matches = re.finditer(SERVICE_REGEX, analysis_result, re.IGNORECASE)
    for match in original_matches:
        service = match.group(1).lower()
        services.add(service)
    
    # Method 5: Check for service names in the original mappings
    for service_name in ORIGINAL_SERVICE_MAPPING.keys():
        if service_name.lower() in analysis_result.lower():
            services.add(service_name.lower())
    
    return list(services)

def map_service_to_code(service):
    """
    Map a service name to its AWS pricing service code with fallback mechanisms
    """
    # Try direct mapping first
    if service.lower() in SERVICE_MAPPING:
        return SERVICE_MAPPING[service.lower()]
    
    # Try variations
    variations = [
        service.lower(),
        service.lower().replace(' ', ''),
        service.lower().replace(' ', '-'),
        service.lower().replace('-', ''),
        service.lower().replace('-', ' ')
    ]
    
    for variation in variations:
        if variation in SERVICE_MAPPING:
            return SERVICE_MAPPING[variation]
    
    # Try to infer the pricing code
    if service.lower().startswith('amazon'):
        base_name = service[7:].strip()  # Remove 'Amazon ' prefix
        return f"Amazon{base_name.title().replace(' ', '').replace('-', '')}"
    elif service.lower().startswith('aws'):
        base_name = service[4:].strip()  # Remove 'AWS ' prefix
        return f"AWS{base_name.title().replace(' ', '').replace('-', '')}"
    
    # Default fallback - try to construct a likely service code
    return f"Amazon{service.title().replace(' ', '').replace('-', '')}"

def map_service_to_quota_code(service):
    """
    Map a service name to its Service Quotas service code with fallback mechanisms
    """
    # Try direct mapping first
    if service.lower() in QUOTA_SERVICE_MAPPING:
        return QUOTA_SERVICE_MAPPING[service.lower()]
    
    # Try variations
    variations = [
        service.lower(),
        service.lower().replace(' ', ''),
        service.lower().replace(' ', '-'),
        service.lower().replace('-', ''),
        service.lower().replace('-', ' ')
    ]
    
    for variation in variations:
        if variation in QUOTA_SERVICE_MAPPING:
            return QUOTA_SERVICE_MAPPING[variation]
    
    # Try to infer the quota code - typically it's the service name without spaces or special formatting
    return service.lower().replace(' ', '').replace('-', '')

def get_resource_config(service, analysis_result):
    """
    Extract resource configuration for a specific service from the analysis result
    """
    config = {}
    
    if service.lower() == 'ec2':
        # Extract EC2 instance type
        instance_type_match = re.search(r'(t[23]\.[a-z]+|m[45]\.[a-z]+|c[45]\.[a-z]+|r[45]\.[a-z]+)', analysis_result, re.IGNORECASE)
        if instance_type_match:
            config['instanceType'] = instance_type_match.group(1).lower()
        else:
            config['instanceType'] = 't3.micro'  # Default
            
        # Extract region
        region_match = re.search(r'(us-east-1|us-east-2|us-west-1|us-west-2|eu-west-1|eu-central-1|ap-northeast-1)', analysis_result, re.IGNORECASE)
        if region_match:
            config['region'] = region_match.group(1).lower()
        else:
            config['region'] = 'us-east-1'  # Default
    
    elif service.lower() == 's3':
        # Extract storage class
        storage_class_match = re.search(r'(standard|intelligent-tiering|standard-ia|one-zone-ia|glacier|deep-archive)', analysis_result, re.IGNORECASE)
        if storage_class_match:
            config['storageClass'] = storage_class_match.group(1).lower()
        else:
            config['storageClass'] = 'standard'  # Default
    
    elif service.lower() == 'rds':
        # Extract DB engine
        db_engine_match = re.search(r'(mysql|postgresql|aurora|oracle|sqlserver)', analysis_result, re.IGNORECASE)
        if db_engine_match:
            config['engine'] = db_engine_match.group(1).lower()
        else:
            config['engine'] = 'mysql'  # Default
            
        # Extract instance class
        instance_class_match = re.search(r'(db\.t[23]\.[a-z]+|db\.m[45]\.[a-z]+|db\.r[45]\.[a-z]+)', analysis_result, re.IGNORECASE)
        if instance_class_match:
            config['instanceClass'] = instance_class_match.group(1).lower()
        else:
            config['instanceClass'] = 'db.t3.micro'  # Default
    
    # Add more service-specific configuration extraction as needed
    # For example, for Lambda:
    elif service.lower() == 'lambda':
        # Extract memory size
        memory_match = re.search(r'(\d+)\s*MB', analysis_result, re.IGNORECASE)
        if memory_match:
            config['memorySize'] = memory_match.group(1)
        else:
            config['memorySize'] = '128'  # Default
            
        # Extract timeout
        timeout_match = re.search(r'timeout\s*[of]*\s*(\d+)\s*seconds', analysis_result, re.IGNORECASE)
        if timeout_match:
            config['timeout'] = timeout_match.group(1)
        else:
            config['timeout'] = '3'  # Default
    
    return config

def build_pricing_filters(service_code, resource_config):
    """
    Build filters for the AWS pricing API based on service and resource configuration
    """
    filters = [
        {'Type': 'TERM_MATCH', 'Field': 'ServiceCode', 'Value': service_code}
    ]
    
    # Get available attributes for this service
    service_attributes = AVAILABLE_PRICING_SERVICES.get(service_code, {}).get('attributes', [])
    
    # Add common filters based on available attributes
    common_attributes = {
        'location': 'US East (N. Virginia)',  # Default location
        'operatingSystem': 'Linux',
        'tenancy': 'Shared',
        'preInstalledSw': 'NA'
    }
    
    # Add filters based on available attributes
    for attr, value in common_attributes.items():
        if attr in service_attributes:
            filters.append({'Type': 'TERM_MATCH', 'Field': attr, 'Value': value})
    
    # Add service-specific filters based on resource_config
    for key, value in resource_config.items():
        # Map resource_config keys to pricing API attribute names
        attr_mapping = {
            'instanceType': 'instanceType',
            'region': 'location',
            'storageClass': 'storageClass',
            'engine': 'databaseEngine',
            'instanceClass': 'instanceType',
            'memorySize': 'memory',
            'timeout': 'timeout'
            # Add more mappings as needed
        }
        
        if key in attr_mapping and attr_mapping[key] in service_attributes:
            # Special handling for region
            if key == 'region':
                location = map_region_to_location(value)
                filters.append({'Type': 'TERM_MATCH', 'Field': 'location', 'Value': location})
            # Special handling for engine
            elif key == 'engine':
                engine = map_rds_engine(value)
                filters.append({'Type': 'TERM_MATCH', 'Field': 'databaseEngine', 'Value': engine})
            else:
                filters.append({'Type': 'TERM_MATCH', 'Field': attr_mapping[key], 'Value': value})
    
    # Service-specific handling
    if service_code == 'AmazonEC2':
        # Add EC2-specific filters
        if 'operatingSystem' in service_attributes and not any(f['Field'] == 'operatingSystem' for f in filters):
            filters.append({'Type': 'TERM_MATCH', 'Field': 'operatingSystem', 'Value': 'Linux'})
        if 'preInstalledSw' in service_attributes and not any(f['Field'] == 'preInstalledSw' for f in filters):
            filters.append({'Type': 'TERM_MATCH', 'Field': 'preInstalledSw', 'Value': 'NA'})
        if 'tenancy' in service_attributes and not any(f['Field'] == 'tenancy' for f in filters):
            filters.append({'Type': 'TERM_MATCH', 'Field': 'tenancy', 'Value': 'Shared'})
        
        # Add instance type if available
        if 'instanceType' in resource_config and 'instanceType' in service_attributes:
            filters.append({'Type': 'TERM_MATCH', 'Field': 'instanceType', 'Value': resource_config['instanceType']})
            
        # Add region if available
        if 'region' in resource_config and 'location' in service_attributes:
            filters.append({'Type': 'TERM_MATCH', 'Field': 'location', 'Value': map_region_to_location(resource_config['region'])})
        elif 'location' in service_attributes:
            filters.append({'Type': 'TERM_MATCH', 'Field': 'location', 'Value': 'US East (N. Virginia)'})
    
    elif service_code == 'AmazonS3':
        # Add S3-specific filters
        if 'storageClass' in resource_config and 'storageClass' in service_attributes:
            filters.append({'Type': 'TERM_MATCH', 'Field': 'storageClass', 'Value': resource_config['storageClass']})
        elif 'storageClass' in service_attributes:
            filters.append({'Type': 'TERM_MATCH', 'Field': 'storageClass', 'Value': 'General Purpose'})
            
        if 'location' in service_attributes and not any(f['Field'] == 'location' for f in filters):
            filters.append({'Type': 'TERM_MATCH', 'Field': 'location', 'Value': 'US East (N. Virginia)'})
    
    elif service_code == 'AmazonRDS':
        # Add RDS-specific filters
        if 'engine' in resource_config and 'databaseEngine' in service_attributes:
            filters.append({'Type': 'TERM_MATCH', 'Field': 'databaseEngine', 'Value': map_rds_engine(resource_config['engine'])})
        elif 'databaseEngine' in service_attributes:
            filters.append({'Type': 'TERM_MATCH', 'Field': 'databaseEngine', 'Value': 'MySQL'})
            
        if 'instanceClass' in resource_config and 'instanceType' in service_attributes:
            filters.append({'Type': 'TERM_MATCH', 'Field': 'instanceType', 'Value': resource_config['instanceClass']})
            
        if 'deploymentOption' in service_attributes and not any(f['Field'] == 'deploymentOption' for f in filters):
            filters.append({'Type': 'TERM_MATCH', 'Field': 'deploymentOption', 'Value': 'Single-AZ'})
        
        if 'location' in service_attributes and not any(f['Field'] == 'location' for f in filters):
            filters.append({'Type': 'TERM_MATCH', 'Field': 'location', 'Value': 'US East (N. Virginia)'})
    
    return filters

def map_region_to_location(region):
    """
    Map AWS region code to location name used in the pricing API
    """
    region_mapping = {
        'us-east-1': 'US East (N. Virginia)',
        'us-east-2': 'US East (Ohio)',
        'us-west-1': 'US West (N. California)',
        'us-west-2': 'US West (Oregon)',
        'eu-west-1': 'EU (Ireland)',
        'eu-central-1': 'EU (Frankfurt)',
        'ap-northeast-1': 'Asia Pacific (Tokyo)',
        'ap-southeast-1': 'Asia Pacific (Singapore)',
        'ap-southeast-2': 'Asia Pacific (Sydney)',
        'sa-east-1': 'South America (Sao Paulo)',
        'ca-central-1': 'Canada (Central)',
        'eu-west-2': 'EU (London)',
        'eu-west-3': 'EU (Paris)',
        'eu-north-1': 'EU (Stockholm)',
        'ap-northeast-2': 'Asia Pacific (Seoul)',
        'ap-northeast-3': 'Asia Pacific (Osaka)',
        'ap-south-1': 'Asia Pacific (Mumbai)',
        'me-south-1': 'Middle East (Bahrain)',
        'af-south-1': 'Africa (Cape Town)'
    }
    return region_mapping.get(region.lower(), 'US East (N. Virginia)')

def map_rds_engine(engine):
    """
    Map RDS engine name to the name used in the pricing API
    """
    engine_mapping = {
        'mysql': 'MySQL',
        'postgresql': 'PostgreSQL',
        'aurora': 'Aurora MySQL',
        'aurora-postgresql': 'Aurora PostgreSQL',
        'oracle': 'Oracle',
        'sqlserver': 'SQL Server',
        'mariadb': 'MariaDB'
    }
    return engine_mapping.get(engine.lower(), 'MySQL')

def get_pricing_with_cache(filters):
    """
    Get pricing information with caching
    """
    if pricing_cache_table is None:
        # If cache table is not available, get pricing directly
        return get_pricing(filters)
    
    # Create a cache key from the filters
    cache_key = json.dumps(sorted(filters, key=lambda x: x['Field']), sort_keys=True)
    
    try:
        # Try to get from cache
        response = pricing_cache_table.get_item(Key={'cache_key': cache_key})
        
        if 'Item' in response:
            item = response['Item']
            timestamp = item.get('timestamp', 0)
            current_time = time.time()
            
            # Check if cache is still valid
            if current_time - timestamp < PRICING_CACHE_TTL:
                logger.info("Using cached pricing data")
                return json.loads(item['pricing_data'])
    except Exception as e:
        logger.warning(f"Error reading from cache: {str(e)}")
    
    # If not in cache or expired, get fresh data
    pricing_data = get_pricing(filters)
    
    # Store in cache
    try:
        pricing_cache_table.put_item(
            Item={
                'cache_key': cache_key,
                'pricing_data': json.dumps(pricing_data, default=handle_decimal),
                'timestamp': Decimal(str(time.time()))
            }
        )
    except Exception as e:
        logger.warning(f"Error writing to cache: {str(e)}")
    
    return pricing_data

def handle_decimal(obj):
    """
    Helper function to handle Decimal objects in JSON serialization
    """
    if isinstance(obj, Decimal):
        return float(obj)
    raise TypeError

def get_pricing(filters):
    """
    Get pricing information from AWS Price List API
    """
    try:
        # Get products
        products_response = pricing.get_products(
            ServiceCode=filters[0]['Value'],
            Filters=filters,
            MaxResults=100
        )
        
        # Process pricing information
        pricing_results = []
        for price_list in products_response.get('PriceList', []):
            price_data = json.loads(price_list)
            
            # Extract product attributes
            attributes = price_data.get('product', {}).get('attributes', {})
            
            # Extract pricing information
            terms = price_data.get('terms', {})
            on_demand = next(iter(terms.get('OnDemand', {}).values()), {})
            price_dimensions = next(iter(on_demand.get('priceDimensions', {}).values()), {})
            
            # Get reserved pricing if available
            reserved = {}
            if 'Reserved' in terms:
                reserved_term = next(iter(terms.get('Reserved', {}).values()), {})
                reserved_price = next(iter(reserved_term.get('priceDimensions', {}).values()), {})
                reserved = {
                    'pricePerUnit': reserved_price.get('pricePerUnit', {}),
                    'unit': reserved_price.get('unit', ''),
                    'description': reserved_price.get('description', '')
                }
            
            pricing_results.append({
                'attributes': attributes,
                'pricing': {
                    'onDemand': {
                        'pricePerUnit': price_dimensions.get('pricePerUnit', {}),
                        'unit': price_dimensions.get('unit', ''),
                        'description': price_dimensions.get('description', '')
                    },
                    'reserved': reserved
                }
            })
        
        return pricing_results
    except Exception as e:
        logger.error(f"Error getting pricing: {str(e)}", exc_info=True)
        return {'error': str(e)}

def ensure_output_bucket_exists():
    """
    Ensure the output S3 bucket exists, creating it if necessary
    """
    try:
        s3.head_bucket(Bucket=OUTPUT_BUCKET)
        logger.info(f"Output bucket {OUTPUT_BUCKET} exists")
    except ClientError as e:
        error_code = e.response['Error']['Code']
        if error_code == '404':
            logger.info(f"Creating output bucket {OUTPUT_BUCKET}")
            s3.create_bucket(Bucket=OUTPUT_BUCKET)
        else:
            logger.error(f"Error checking output bucket: {str(e)}")
            raise

def store_output(output):
    """
    Store the analysis output in S3
    """
    output_key = f"{OUTPUT_PREFIX}analysis_{uuid.uuid4()}.json"
    
    # Convert to JSON string
    output_json = json.dumps(output, default=handle_decimal)
    
    # Upload to S3
    s3.put_object(
        Bucket=OUTPUT_BUCKET,
        Key=output_key,
        Body=output_json,
        ContentType='application/json'
    )
    
    return f"s3://{OUTPUT_BUCKET}/{output_key}"

def estimate_total_costs(pricing_data, analysis_result):
    """
    Estimate the total monthly cost of all services based on pricing data and analysis
    
    Returns:
        dict: Containing estimated costs, assumptions, and disclaimers
    """
    total_estimated_cost = 0.0
    service_costs = {}
    assumptions = []
    
    # Extract usage patterns from analysis
    usage_patterns = extract_usage_patterns(analysis_result)
    
    # Process each service
    for service, prices in pricing_data.items():
        service_cost = 0.0
        service_assumptions = []
        
        # Skip services with error in pricing
        if isinstance(prices, dict) and 'error' in prices:
            service_costs[service] = {
                "estimated_monthly_cost": 0.0,
                "assumptions": [f"Could not estimate cost: {prices['error']}"]
            }
            assumptions.append(f"{service}: Could not estimate cost due to pricing API error")
            continue
            
        # Skip empty price lists
        if not prices or not isinstance(prices, list):
            service_costs[service] = {
                "estimated_monthly_cost": 0.0,
                "assumptions": ["No pricing information available"]
            }
            assumptions.append(f"{service}: No pricing information available")
            continue
        
        # Get service-specific usage
        service_usage = usage_patterns.get(service, {})
        
        # Default usage assumptions if not specified
        if not service_usage:
            if service.lower() == 'ec2':
                service_usage = {'hours': 730, 'instances': 1}  # 730 hours in a month
                service_assumptions.append("Assumed 1 instance running 24/7")
            elif service.lower() == 's3':
                service_usage = {'storage_gb': 100, 'requests': 10000}
                service_assumptions.append("Assumed 100 GB storage and 10,000 requests per month")
            elif service.lower() == 'rds':
                service_usage = {'hours': 730, 'instances': 1}
                service_assumptions.append("Assumed 1 database instance running 24/7")
            elif service.lower() == 'lambda':
                service_usage = {'invocations': 1000000, 'avg_duration_ms': 200, 'memory_mb': 128}
                service_assumptions.append("Assumed 1M invocations, 200ms avg duration, 128MB memory")
            elif service.lower() == 'dynamodb':
                service_usage = {'read_capacity_units': 5, 'write_capacity_units': 5, 'storage_gb': 10}
                service_assumptions.append("Assumed 5 RCU, 5 WCU, 10GB storage")
            else:
                service_usage = {'usage_factor': 1.0}
                service_assumptions.append(f"Used default pricing for {service}")
        
        # Calculate cost based on service type
        if service.lower() == 'ec2':
            # Use the first price option for simplicity
            if prices and len(prices) > 0:
                price_info = prices[0].get('pricing', {}).get('onDemand', {})
                if price_info:
                    hourly_rate = float(price_info.get('pricePerUnit', {}).get('USD', 0))
                    hours = service_usage.get('hours', 730)
                    instances = service_usage.get('instances', 1)
                    service_cost = hourly_rate * hours * instances
        elif service.lower() == 's3':
            # Simplified S3 pricing
            if prices and len(prices) > 0:
                storage_price = float(prices[0].get('pricing', {}).get('onDemand', {}).get('pricePerUnit', {}).get('USD', 0))
                storage_gb = service_usage.get('storage_gb', 100)
                service_cost = storage_price * storage_gb
        else:
            # Generic calculation for other services
            if prices and len(prices) > 0:
                price_info = prices[0].get('pricing', {}).get('onDemand', {})
                if price_info:
                    unit_price = float(price_info.get('pricePerUnit', {}).get('USD', 0))
                    usage_factor = service_usage.get('usage_factor', 1.0)
                    service_cost = unit_price * usage_factor * 730  # Multiply by hours in month for hourly services
        
        # Add service cost to total
        total_estimated_cost += service_cost
        
        # Store service-specific cost info
        service_costs[service] = {
            "estimated_monthly_cost": service_cost,
            "assumptions": service_assumptions
        }
        
        # Add service assumptions to global assumptions
        assumptions.extend(service_assumptions)
    
    # Prepare result
    result = {
        "total_estimated_monthly_cost": total_estimated_cost,
        "service_costs": service_costs,
        "assumptions": assumptions,
        "disclaimers": [
            "This is a rough estimate based on limited information",
            "Actual costs may vary based on usage patterns, data transfer, and other factors",
            "Reserved instances, savings plans, and free tier are not considered",
            "Regional pricing differences may apply"
        ]
    }
    
    return result

def extract_usage_patterns(analysis_result):
    """
    Extract usage patterns from the analysis result
    
    Returns:
        dict: Service usage patterns
    """
    usage_patterns = {}
    
    # Look for EC2 instance counts and types
    ec2_instances = re.findall(r'(\d+)\s*(?:x\s*)?EC2\s*instances?', analysis_result, re.IGNORECASE)
    ec2_type = re.search(r'(t[23]\.[a-z]+|m[45]\.[a-z]+|c[45]\.[a-z]+|r[45]\.[a-z]+)', analysis_result, re.IGNORECASE)
    
    if ec2_instances:
        instances = int(ec2_instances[0])
        usage_patterns['ec2'] = {'hours': 730, 'instances': instances}
    elif ec2_type:
        usage_patterns['ec2'] = {'hours': 730, 'instances': 1}
    
    # Look for S3 storage estimates
    s3_storage = re.search(r'(\d+)\s*(?:GB|TB|PB)\s*(?:of\s*)?(?:S3|storage)', analysis_result, re.IGNORECASE)
    if s3_storage:
        size = int(s3_storage.group(1))
        unit = s3_storage.group(2).upper() if s3_storage.group(2) else 'GB'
        
        # Convert to GB
        if unit == 'TB':
            size *= 1024
        elif unit == 'PB':
            size *= 1024 * 1024
            
        usage_patterns['s3'] = {'storage_gb': size, 'requests': 10000}
    
    # Look for RDS instance counts
    rds_instances = re.findall(r'(\d+)\s*(?:x\s*)?RDS\s*instances?', analysis_result, re.IGNORECASE)
    if rds_instances:
        instances = int(rds_instances[0])
        usage_patterns['rds'] = {'hours': 730, 'instances': instances}
    
    # Look for Lambda invocations
    lambda_invocations = re.search(r'(\d+)\s*(?:K|M|B)?\s*(?:Lambda\s*)?invocations', analysis_result, re.IGNORECASE)
    if lambda_invocations:
        count = int(lambda_invocations.group(1))
        unit = lambda_invocations.group(2) if lambda_invocations.group(2) else ''
        
        # Convert to actual count
        if unit and unit.upper() == 'K':
            count *= 1000
        elif unit and unit.upper() == 'M':
            count *= 1000000
        elif unit and unit.upper() == 'B':
            count *= 1000000000
            
        usage_patterns['lambda'] = {'invocations': count, 'avg_duration_ms': 200, 'memory_mb': 128}
    
    return usage_patterns

def query_bedrock_with_retry(prompt, max_retries=None, retry_delay=None):
    """
    Query Bedrock with retry logic
    """
    if max_retries is None:
        max_retries = MAX_RETRIES
    if retry_delay is None:
        retry_delay = RETRY_DELAY
        
    for attempt in range(max_retries):
        try:
            response = bedrock.invoke_model(
                modelId=BEDROCK_MODEL_ID,
                body=json.dumps(prompt)
            )
            response_body = json.loads(response['body'].read())
            
            # Extract the assistant's message content
            if 'content' in response_body:
                return response_body['content'][0]['text']
            else:
                return response_body.get('completion', '')
        except Exception as e:
            if attempt < max_retries - 1:
                logger.warning(f"Bedrock query failed (attempt {attempt+1}/{max_retries}): {str(e)}. Retrying in {retry_delay}s...")
                time.sleep(retry_delay)
            else:
                logger.error(f"Bedrock query failed after {max_retries} attempts: {str(e)}")
                raise

def get_service_quotas(services):
    """
    Get default quotas for the identified AWS services
    
    Args:
        services (list): List of service names
    
    Returns:
        dict: Service quotas information
    """
    service_quotas_data = {}
    try:
        service_quotas_client = boto3.client('service-quotas')
    except Exception as e:
        logger.warning(f"Could not initialize Service Quotas client: {str(e)}")
        # Return fallback quotas for all services
        for service in services:
            fallback_quotas = get_fallback_quotas(service)
            if fallback_quotas:
                service_quotas_data[service] = fallback_quotas
        return service_quotas_data
    
    for service in services:
        service_code = map_service_to_quota_code(service)
        if service_code:
            try:
                # Get default quotas for the service
                quotas = get_default_quotas_for_service(service_quotas_client, service_code)
                
                # Filter and organize quotas
                relevant_quotas = filter_relevant_quotas(service, quotas)
                
                if relevant_quotas:
                    service_quotas_data[service] = relevant_quotas
                else:
                    # If no quotas found, use fallback
                    fallback_quotas = get_fallback_quotas(service)
                    if fallback_quotas:
                        service_quotas_data[service] = fallback_quotas
            except Exception as e:
                logger.warning(f"Error fetching quotas for {service} ({service_code}): {str(e)}")
                # Add fallback default quotas for common services
                fallback_quotas = get_fallback_quotas(service)
                if fallback_quotas:
                    service_quotas_data[service] = fallback_quotas
    
    return service_quotas_data

def get_default_quotas_for_service(client, service_code):
    """
    Get default quotas for a specific service
    
    Args:
        client: Service Quotas boto3 client
        service_code (str): Service code
    
    Returns:
        list: List of quota objects
    """
    quotas = []
    paginator = client.get_paginator('list_aws_default_service_quotas')
    
    try:
        for page in paginator.paginate(ServiceCode=service_code):
            quotas.extend(page.get('Quotas', []))
        return quotas
    except client.exceptions.ServiceException:
        logger.warning(f"Service {service_code} not found in Service Quotas")
        return []
    except Exception as e:
        logger.warning(f"Error getting quotas for {service_code}: {str(e)}")
        return []

def filter_relevant_quotas(service, quotas):
    """
    Filter and organize relevant quotas for a service
    
    Args:
        service (str): Service name
        quotas (list): List of quota objects
    
    Returns:
        list: Filtered and organized quotas
    """
    # Define keywords for important quotas per service
    service_keywords = {
        "ec2": ["instances", "vcpu", "volume", "snapshot", "address", "security group"],
        "s3": ["bucket", "objects", "tags", "lifecycle", "policy"],
        "rds": ["instance", "storage", "cluster", "snapshot", "subnet", "parameter"],
        "lambda": ["function", "memory", "timeout", "concurrent", "code size"],
        "dynamodb": ["table", "capacity", "throughput", "index", "partition"],
        "vpc": ["vpc", "subnet", "gateway", "endpoint", "peering"],
        "iam": ["role", "policy", "user", "group", "instance profile"]
    }
    
    # Get keywords for this service or use default
    keywords = service_keywords.get(service.lower(), [])
    
    # Filter quotas by keywords if available
    filtered_quotas = []
    if keywords:
        for quota in quotas:
            if any(keyword.lower() in quota.get('QuotaName', '').lower() for keyword in keywords):
                filtered_quotas.append({
                    'name': quota.get('QuotaName'),
                    'value': quota.get('Value'),
                    'adjustable': quota.get('Adjustable', False),
                    'unit': extract_unit_from_name(quota.get('QuotaName', ''))
                })
    else:
        # If no keywords defined, take the first 10 quotas
        for quota in quotas[:10]:
            filtered_quotas.append({
                'name': quota.get('QuotaName'),
                'value': quota.get('Value'),
                'adjustable': quota.get('Adjustable', False),
                'unit': extract_unit_from_name(quota.get('QuotaName', ''))
            })
    
    # Sort by adjustability and name
    filtered_quotas.sort(key=lambda x: (not x['adjustable'], x['name']))
    
    return filtered_quotas[:10]  # Return at most 10 quotas per service

def extract_unit_from_name(name):
    """
    Extract unit from quota name if possible
    """
    # Common units that might appear in quota names
    units = ['per second', 'per account', 'per region', 'GB', 'MB', 'KB', 'TB']
    
    for unit in units:
        if unit in name.lower():
            return unit
    
    return ""

def get_fallback_quotas(service):
    """
    Provide fallback default quotas for common services
    """
    fallback_quotas = {
        "ec2": [
            {'name': 'Running On-Demand Standard (A, C, D, H, I, M, R, T, Z) instances', 'value': 5, 'adjustable': True, 'unit': 'per account'},
            {'name': 'EC2-VPC Elastic IPs', 'value': 5, 'adjustable': True, 'unit': 'per account'},
            {'name': 'Security Groups per VPC', 'value': 2500, 'adjustable': False, 'unit': 'per VPC'}
        ],
        "s3": [
            {'name': 'Buckets', 'value': 100, 'adjustable': True, 'unit': 'per account'},
            {'name': 'Account-level bucket public access block', 'value': 1, 'adjustable': False, 'unit': 'per account'}
        ],
        "lambda": [
            {'name': 'Concurrent executions', 'value': 1000, 'adjustable': True, 'unit': 'per region'},
            {'name': 'Function timeout', 'value': 900, 'adjustable': False, 'unit': 'seconds'},
            {'name': 'Function memory', 'value': 10240, 'adjustable': False, 'unit': 'MB'}
        ],
        "dynamodb": [
            {'name': 'Tables per account', 'value': 2500, 'adjustable': True, 'unit': 'per account'},
            {'name': 'Maximum table size', 'value': -1, 'adjustable': False, 'unit': 'GB'},  # Unlimited
            {'name': 'Read capacity units per table', 'value': 40000, 'adjustable': True, 'unit': 'per table'}
        ],
        "vpc": [
            {'name': 'VPCs per region', 'value': 5, 'adjustable': True, 'unit': 'per region'},
            {'name': 'Subnets per VPC', 'value': 200, 'adjustable': True, 'unit': 'per VPC'}
        ],
                "rds": [
            {'name': 'DB instances', 'value': 40, 'adjustable': True, 'unit': 'per account'},
            {'name': 'Storage quota', 'value': 100000, 'adjustable': True, 'unit': 'GB'}
        ],
        "iam": [
            {'name': 'IAM roles', 'value': 1000, 'adjustable': True, 'unit': 'per account'},
            {'name': 'IAM users', 'value': 5000, 'adjustable': True, 'unit': 'per account'},
            {'name': 'IAM groups', 'value': 300, 'adjustable': False, 'unit': 'per account'}
        ],
        "sqs": [
            {'name': 'Standard queues per region', 'value': 1000, 'adjustable': True, 'unit': 'per region'},
            {'name': 'Messages per queue (backlog)', 'value': -1, 'adjustable': False, 'unit': 'messages'}  # Unlimited
        ],
        "sns": [
            {'name': 'Topics per account', 'value': 100000, 'adjustable': True, 'unit': 'per account'},
            {'name': 'Subscriptions per topic', 'value': 12500000, 'adjustable': True, 'unit': 'per topic'}
        ],
        "cloudfront": [
            {'name': 'Distributions per account', 'value': 200, 'adjustable': True, 'unit': 'per account'},
            {'name': 'Cache behaviors per distribution', 'value': 25, 'adjustable': True, 'unit': 'per distribution'}
        ],
        "api gateway": [
            {'name': 'APIs per account', 'value': 600, 'adjustable': True, 'unit': 'per account'},
            {'name': 'Routes per API', 'value': 300, 'adjustable': True, 'unit': 'per API'}
        ],
        "route53": [
            {'name': 'Hosted zones', 'value': 500, 'adjustable': True, 'unit': 'per account'},
            {'name': 'Records per hosted zone', 'value': 10000, 'adjustable': True, 'unit': 'per hosted zone'}
        ]
    }
    
    return fallback_quotas.get(service.lower())

def build_recommendations_prompt(analysis, pricing_data, cost_estimate=None, service_quotas=None):
    """
    Build a prompt for Bedrock to generate optimization recommendations
    """
    # Create a simplified pricing summary
    pricing_summary = "Pricing Information:\n"
    for service, prices in pricing_data.items():
        pricing_summary += f"\n{service.upper()} PRICING:\n"
        if isinstance(prices, list) and prices:
            for i, price in enumerate(prices[:3]):
                pricing_summary += f"Option {i+1}:\n"
                if 'attributes' in price:
                    for k, v in price.get('attributes', {}).items():
                        pricing_summary += f"  {k}: {v}\n"
                if 'pricing' in price:
                    pricing_info = price.get('pricing', {})
                    if 'onDemand' in pricing_info:
                        on_demand = pricing_info['onDemand']
                        pricing_summary += f"  On-Demand: {on_demand.get('pricePerUnit', {}).get('USD', 'N/A')} USD per {on_demand.get('unit', 'unit')}\n"
                    if 'reserved' in pricing_info:
                        reserved = pricing_info['reserved']
                        pricing_summary += f"  Reserved: {reserved.get('pricePerUnit', {}).get('USD', 'N/A')} USD per {reserved.get('unit', 'unit')}\n"
        elif isinstance(prices, dict) and 'error' in prices:
            pricing_summary += f"  Error retrieving pricing: {prices['error']}\n"
    
    # Add cost estimation summary if available
    cost_summary = ""
    if cost_estimate:
        cost_summary = f"\nESTIMATED MONTHLY COST: \\\${cost_estimate['total_estimated_monthly_cost']:.2f} USD\n\n"
        
        # Add per-service costs
        cost_summary += "Service Cost Breakdown:\n"
        for service, service_cost in cost_estimate['service_costs'].items():
            cost_summary += f"- {service}: \\\${service_cost['estimated_monthly_cost']:.2f} USD\n"
        
        # Add assumptions
        cost_summary += "\nAssumptions:\n"
        for assumption in cost_estimate['assumptions'][:10]:  # Limit to top 10 assumptions
            cost_summary += f"- {assumption}\n"
        
        # Add disclaimers
        cost_summary += "\nDisclaimers:\n"
        for disclaimer in cost_estimate['disclaimers']:
            cost_summary += f"- {disclaimer}\n"
    
    # Add service quotas information if available
    quotas_summary = ""
    if service_quotas:
        quotas_summary = "\nSERVICE QUOTAS (Default Limits):\n"
        
        for service, quotas in service_quotas.items():
            quotas_summary += f"\n{service.upper()} QUOTAS:\n"
            
            if isinstance(quotas, list) and quotas:
                for quota in quotas[:5]:  # Limit to 5 most important quotas per service
                    name = quota.get('name', 'Unknown')
                    value = quota.get('value', 'N/A')
                    unit = quota.get('unit', '')
                    adjustable = "Adjustable" if quota.get('adjustable', False) else "Not adjustable"
                    
                    quotas_summary += f"- {name}: {value} {unit} ({adjustable})\n"
            else:
                quotas_summary += "  No quota information available\n"
    
    prompt = {
        "anthropic_version": "bedrock-2023-05-31",
        "max_tokens": 2000,
        "messages": [
            {
                "role": "user",
                "content": f"""Based on the following infrastructure analysis, pricing information, cost estimates, and service quotas, 
provide detailed optimization recommendations to improve cost efficiency, performance, security, and reliability.

Infrastructure Analysis:
{analysis}

{pricing_summary}

{cost_summary}

{quotas_summary}

Please provide specific, actionable recommendations in these categories:
1. Cost optimization - Include specific instance right-sizing, reserved instances, savings plans, and storage optimizations
2. Performance improvements - Suggest architecture changes to improve performance
3. Security enhancements - Identify potential security issues and recommend solutions
4. Reliability and high availability - Recommend changes to improve system reliability
5. Architecture best practices - Suggest AWS Well-Architected Framework improvements
6. Service quota considerations - Highlight any service quotas that might impact the architecture and how to address them

For each recommendation, explain:
- The specific issue or opportunity
- The recommended change with specific AWS services or configurations
- The expected benefit (quantify if possible)
- Implementation approach and complexity (low, medium, high)

Include a section at the beginning with a summary of the estimated monthly cost and key cost-saving opportunities."""
            }
        ]
    }
    return prompt
