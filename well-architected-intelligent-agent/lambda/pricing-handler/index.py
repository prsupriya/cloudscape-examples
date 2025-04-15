import boto3
import json
import re
import uuid
import os
import time
import logging
from botocore.exceptions import ClientError
from urllib.parse import unquote_plus

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

# Initialize the pricing cache table
try:
    pricing_cache_table = ensure_pricing_cache_table_exists()
except Exception as e:
    logger.warning(f"Could not initialize pricing cache table: {str(e)}")
    pricing_cache_table = None

# Enhanced regex for AWS service detection
SERVICE_REGEX = r'\b(EC2|S3|RDS|Lambda|DynamoDB|ECS|EKS|SQS|SNS|CloudFront|API Gateway|Route53|CloudWatch|IAM|VPC|ELB|ALB|NLB|CloudFormation|Step Functions|Kinesis|Glue|Athena|EMR|Redshift|ElastiCache|Neptune|DocumentDB|MSK|OpenSearch|Elasticsearch|CodePipeline|CodeBuild|CodeDeploy|CodeCommit|Amplify|AppSync|EventBridge|CloudTrail|GuardDuty|WAF|Shield|Secrets Manager|KMS|ACM|Cognito|SES|Pinpoint)\b'

# Expanded service mapping
SERVICE_MAPPING = {
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

def lambda_handler(event, context):
    """
    Main Lambda handler function that processes S3 events
    """
    try:
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
        
        # Step 5: Generate cost estimation
        cost_estimate = estimate_total_costs(pricing_data, analysis_result)
        
        # Step 6: Generate recommendations with cost information
        recommendations_prompt = build_recommendations_prompt(analysis_result, pricing_data, cost_estimate)
        recommendations = query_bedrock_with_retry(recommendations_prompt)
        
        # Step 7: Store output
        output = {
            "source": f"s3://{s3_bucket}/{s3_key}",
            "analysis": analysis_result,
            "services": services,
            "pricing": pricing_data,
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
                "estimated_monthly_cost": cost_estimate["total_estimated_monthly_cost"]
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
        if block['BlockType'] == 'LINE':
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

def estimate_total_costs(pricing_data, analysis_result):
    """
    Estimate the total monthly cost of all services based on pricing data and analysis
    
    Returns:
        dict: Containing estimated costs, assumptions, and disclaimers
    """
    total_estimated_cost = 0.0
    service_costs = {}
    assumptions = []
    
    # For each service with pricing data
    for service, prices in pricing_data.items():
        service_cost = 0.0
        service_assumptions = []
        
        if isinstance(prices, list) and prices:
            # Get the first pricing option as default
            price_option = prices[0]
            
            # Extract usage estimates from the analysis
            usage_estimate = estimate_service_usage(service, analysis_result)
            
            # Get the price information
            if 'pricing' in price_option and 'onDemand' in price_option['pricing']:
                on_demand = price_option['pricing']['onDemand']
                unit_price_str = on_demand.get('pricePerUnit', {}).get('USD', '0')
                
                try:
                    # Convert price string to float
                    unit_price = float(unit_price_str)
                    unit_type = on_demand.get('unit', 'unit')
                    
                    # Calculate monthly cost based on unit type and usage estimate
                    if unit_type.lower() == 'hrs' or unit_type.lower() == 'hour':
                        # Hourly pricing - assume 730 hours per month
                        monthly_hours = 730 * usage_estimate.get('count', 1)
                        service_cost = unit_price * monthly_hours
                        service_assumptions.append(f"Running for 730 hours per month (24/7)")
                    elif 'gb-mo' in unit_type.lower():
                        # GB-month pricing
                        service_cost = unit_price * usage_estimate.get('size_gb', 1)
                        service_assumptions.append(f"Storage size of {usage_estimate.get('size_gb', 1)} GB")
                    elif 'requests' in unit_type.lower():
                        # Per-request pricing
                        monthly_requests = usage_estimate.get('requests', 100000)
                        service_cost = unit_price * monthly_requests / 1000  # Usually priced per 1000 requests
                        service_assumptions.append(f"Approximately {monthly_requests} requests per month")
                    else:
                        # Default calculation
                        service_cost = unit_price * usage_estimate.get('count', 1)
                        service_assumptions.append(f"Using {usage_estimate.get('count', 1)} units")
                    
                    # Add service attributes to assumptions
                    for key, value in price_option.get('attributes', {}).items():
                        if key in ['instanceType', 'vcpu', 'memory', 'storageClass', 'volumeType', 'databaseEngine']:
                            service_assumptions.append(f"{key}: {value}")
                
                except (ValueError, TypeError):
                    service_cost = 0.0
                    service_assumptions.append("Could not calculate price - using placeholder")
        
        # Add to total cost
        total_estimated_cost += service_cost
        service_costs[service] = {
            "estimated_monthly_cost": service_cost,
            "assumptions": service_assumptions
        }
        assumptions.extend(service_assumptions)
    
    # Add general assumptions
    general_assumptions = [
        "All services run 24/7 unless otherwise specified",
        "Data transfer costs not included",
        "Free tier benefits not applied",
        "On-demand pricing used (no reserved instances or savings plans)"
    ]
    
    disclaimers = [
        "This cost estimate is approximate and for informational purposes only.",
        "Actual AWS billing may vary based on usage patterns, data transfer, request patterns, and other factors.",
        "This estimate doesn't account for AWS Free Tier benefits, which may reduce actual costs.",
        "Prices are based on current public AWS pricing and may change over time.",
        "For a more accurate estimate, use the AWS Pricing Calculator or contact AWS."
    ]
    
    return {
        "total_estimated_monthly_cost": round(total_estimated_cost, 2),
        "service_costs": service_costs,
        "assumptions": list(set(assumptions + general_assumptions)),  # Remove duplicates
        "disclaimers": disclaimers
    }

def estimate_service_usage(service, analysis_result):
    """
    Estimate service usage based on analysis text
    
    Returns:
        dict: Containing usage estimates
    """
    # Default usage estimates
    default_estimates = {
        "ec2": {"count": 1, "hours": 730},
        "rds": {"count": 1, "hours": 730, "size_gb": 20},
        "s3": {"size_gb": 100, "requests": 100000},
        "lambda": {"invocations": 1000000, "avg_duration_ms": 500, "memory_mb": 128},
        "dynamodb": {"size_gb": 10, "rcu": 5, "wcu": 5, "requests": 300000},
        "cloudfront": {"data_gb": 100, "requests": 1000000},
        "eks": {"clusters": 1, "nodes": 3},
        "ecs": {"tasks": 3},
        "sqs": {"requests": 1000000},
        "sns": {"requests": 1000000},
        "cloudwatch": {"metrics": 10, "logs_gb": 5},
    }
    
    service_lower = service.lower()
    
    # Try to extract more accurate usage information from the analysis text
    if service_lower in ["ec2", "rds", "elasticache"]:
        # Look for instance count
        count_match = re.search(rf'(?i)(\d+)\s+{service}\s+instances?', analysis_result)
        if count_match:
            count = int(count_match.group(1))
            return {"count": count, "hours": 730}
    
    elif service_lower == "s3":
        # Look for storage size
        size_match = re.search(r'(\d+)\s*(GB|TB|PB)\s+(?:of\s+)?(?:S3|storage)', analysis_result, re.IGNORECASE)
        if size_match:
            size = float(size_match.group(1))
            unit = size_match.group(2).upper()
            if unit == "TB":
                size *= 1000
            elif unit == "PB":
                size *= 1000000
            return {"size_gb": size, "requests": 100000}
    
    elif service_lower == "lambda":
        # Look for invocation count and memory
        invocation_match = re.search(r'(\d+)\s+(?:lambda\s+)?invocations', analysis_result, re.IGNORECASE)
        memory_match = re.search(r'lambda.*?(\d+)\s*MB', analysis_result, re.IGNORECASE)
        
        invocations = int(invocation_match.group(1)) if invocation_match else 1000000
        memory_mb = int(memory_match.group(1)) if memory_match else 128
        
        return {"invocations": invocations, "avg_duration_ms": 500, "memory_mb": memory_mb}
    
    # Return default estimates if service exists in defaults, otherwise return generic count
    return default_estimates.get(service_lower, {"count": 1})

def query_bedrock_with_retry(prompt, retries=None):
    """
    Query Amazon Bedrock with a prompt and retry on failure
    """
    if retries is None:
        retries = MAX_RETRIES
        
    last_exception = None
    for attempt in range(retries):
        try:
            return query_bedrock(prompt)
        except Exception as e:
            last_exception = e
            logger.warning(f"Bedrock query failed (attempt {attempt+1}/{retries}): {str(e)}")
            if attempt < retries - 1:
                time.sleep(RETRY_DELAY * (2 ** attempt))  # Exponential backoff
    
    logger.error(f"All Bedrock query attempts failed: {str(last_exception)}")
    raise last_exception

def query_bedrock(prompt):
    """
    Query Amazon Bedrock with a prompt
    """
    try:
        response = bedrock.invoke_model(
            modelId=BEDROCK_MODEL_ID,
            body=json.dumps(prompt)
        )
        response_body = json.loads(response['body'].read())
        return response_body['content'][0]['text']
    except Exception as e:
        logger.error(f"Error querying Bedrock: {str(e)}")
        raise

def get_services_from_analysis(analysis):
    """
    Extract AWS service names from the analysis text
    """
    services = re.findall(SERVICE_REGEX, analysis, re.IGNORECASE)
    services = [s.lower() for s in services]
    return list(set(services))

def map_service_to_code(service):
    """
    Map a service name to its pricing API service code
    """
    return SERVICE_MAPPING.get(service.lower())

def get_resource_config(service, analysis):
    """
    Extract resource configuration for a service from the analysis
    """
    service_patterns = {
        "ec2": [
            rf'(?i){service}.*?(?:instance|type).*?([a-z][0-9][a-z]?\.(?:nano|micro|small|medium|large|xlarge|[0-9]+xlarge))',
            rf'(?i)(?:instance|type).*?([a-z][0-9][a-z]?\.(?:nano|micro|small|medium|large|xlarge|[0-9]+xlarge)).*?{service}'
        ],
        "rds": [
            rf'(?i){service}.*?(?:instance|type|db).*?([a-z][0-9][a-z]?\.(?:nano|micro|small|medium|large|xlarge|[0-9]+xlarge))',
            rf'(?i){service}.*?(?:engine).*?(mysql|postgres|aurora|oracle|sqlserver)'
        ],
        "s3": [
            rf'(?i){service}.*?(?:storage class|tier).*?(standard|intelligent|infrequent access|glacier|deep archive)',
            rf'(?i){service}.*?(?:size|capacity).*?([0-9]+\s*(?:GB|TB|PB))'
        ],
        "lambda": [
            rf'(?i){service}.*?(?:memory).*?([0-9]+\s*(?:MB|GB))',
            rf'(?i){service}.*?(?:timeout).*?([0-9]+\s*(?:seconds|minutes))'
        ],
        "dynamodb": [
            rf'(?i){service}.*?(?:capacity|mode).*?(provisioned|on-demand)',
            rf'(?i){service}.*?(?:RCU|WCU).*?([0-9]+)'
        ]
    }
    
    # Get patterns for this service or use default pattern
    patterns = service_patterns.get(service.lower(), [
        rf'(?i){service}.*?(?:instance|type|configuration|size).*?([a-z0-9\.\-]+)'
    ])
    
    # Try each pattern
    for pattern in patterns:
        match = re.search(pattern, analysis)
        if match:
            return match.group(1).strip()
    
    return "standard"  # Default configuration

def build_pricing_filters(service_code, resource_config):
    """
    Build filters for the pricing API based on service and resource configuration
    """
    filters = {
        'ServiceCode': service_code,
        'Filters': []
    }
    
    # Add service-specific filters
    if service_code == 'AmazonEC2':
        instance_type = resource_config if resource_config else 't3.micro'
        filters['Filters'] = [
            {
                'Type': 'TERM_MATCH',
                'Field': 'instanceType',
                'Value': instance_type
            },
            {
                'Type': 'TERM_MATCH',
                'Field': 'operatingSystem',
                'Value': 'Linux'
            },
            {
                'Type': 'TERM_MATCH',
                'Field': 'tenancy',
                'Value': 'Shared'
            }
        ]
    elif service_code == 'AmazonS3':
        storage_class = 'General Purpose'
        if resource_config and any(term in resource_config.lower() for term in ['standard', 'intelligent', 'infrequent', 'glacier', 'archive']):
            if 'intelligent' in resource_config.lower():
                storage_class = 'Intelligent-Tiering'
            elif 'infrequent' in resource_config.lower():
                storage_class = 'Standard - Infrequent Access'
            elif 'glacier' in resource_config.lower():
                storage_class = 'Glacier'
            elif 'deep archive' in resource_config.lower():
                storage_class = 'Glacier Deep Archive'
                
        filters['Filters'] = [
            {
                'Type': 'TERM_MATCH',
                'Field': 'storageClass',
                'Value': storage_class
            }
        ]
    elif service_code == 'AmazonRDS':
        db_instance_class = resource_config if resource_config else 'db.t3.micro'
        if not db_instance_class.startswith('db.'):
            db_instance_class = 'db.' + db_instance_class
            
        filters['Filters'] = [
            {
                'Type': 'TERM_MATCH',
                'Field': 'instanceType',
                'Value': db_instance_class
            },
            {
                'Type': 'TERM_MATCH',
                'Field': 'deploymentOption',
                'Value': 'Single-AZ'
            }
        ]
    elif service_code == 'AWSLambda':
        filters['Filters'] = [
            {
                'Type': 'TERM_MATCH',
                'Field': 'usagetype',
                'Value': 'Lambda-GB-Second'
            }
        ]
    elif service_code == 'AmazonDynamoDB':
        filters['Filters'] = [
            {
                'Type': 'TERM_MATCH',
                'Field': 'group',
                'Value': 'DDB-ReadUnits'
            }
        ]
    
    return filters

from decimal import Decimal

def get_pricing_with_cache(filters):
    """
    Get pricing information with caching support
    """
    if not pricing_cache_table:
        return get_pricing(filters)
        
    # Create a cache key from the filters
    cache_key = json.dumps(filters, sort_keys=True)
    
    try:
        # Try to get from cache
        response = pricing_cache_table.get_item(Key={'cache_key': cache_key})
        
        if 'Item' in response:
            item = response['Item']
            # Check if cache is still valid
            if time.time() - item['timestamp'] < PRICING_CACHE_TTL:
                logger.info("Using cached pricing data")
                return item['pricing_data']
    except Exception as e:
        logger.warning(f"Error accessing pricing cache: {str(e)}")
    
    # If not in cache or expired, get fresh data
    pricing_data = get_pricing(filters)
    
    # Store in cache
    try:
        # Convert timestamp to Decimal for DynamoDB compatibility
        pricing_cache_table.put_item(
            Item={
                'cache_key': cache_key,
                'pricing_data': pricing_data,
                'timestamp': Decimal(str(time.time()))  # Convert float to Decimal
            }
        )
    except Exception as e:
        logger.warning(f"Error storing in pricing cache: {str(e)}")
    
    return pricing_data


def get_pricing(filters):
    """
    Get pricing information from AWS Price List API
    """
    try:
        if not validate_filters(filters):
            return {"error": "Invalid pricing filters"}
            
        pricing_data = []
        next_token = None
        
        # Use pagination to get all results
        for i in range(5):  # Limit to 5 pages to avoid excessive API calls
            if next_token:
                pricing_response = pricing.get_products(
                    ServiceCode=filters.get('ServiceCode'),
                    Filters=filters.get('Filters', []),
                    NextToken=next_token
                )
            else:
                pricing_response = pricing.get_products(
                    ServiceCode=filters.get('ServiceCode'),
                    Filters=filters.get('Filters', [])
                )
            
            # Process this page of results
            pricing_data.extend(process_pricing_response(pricing_response))
            
            # Check if there are more results
            if 'NextToken' in pricing_response:
                next_token = pricing_response['NextToken']
            else:
                break
        
        return pricing_data
    except Exception as e:
        logger.error(f"Error getting pricing: {str(e)}", exc_info=True)
        return {"error": str(e)}

def validate_filters(filters):
    """
    Validate pricing filters
    """
    if not filters or not isinstance(filters, dict):
        return False
    if 'ServiceCode' not in filters:
        return False
    return True

def process_pricing_response(response):
    """
    Process the pricing API response
    """
    try:
        products = []
        for price_item in response.get('PriceList', []):
            if isinstance(price_item, str):
                product = json.loads(price_item)
                
                # Extract the most relevant pricing information
                simplified_product = {
                    'sku': product.get('product', {}).get('sku'),
                    'productFamily': product.get('product', {}).get('productFamily'),
                    'attributes': extract_important_attributes(product.get('product', {}).get('attributes', {})),
                    'pricing': extract_simplified_pricing(product.get('terms', {}))
                }
                
                products.append(simplified_product)
        
        # Return a simplified version with just the first few products
        return products[:5] if products else []
    except Exception as e:
        logger.error(f"Error processing pricing response: {str(e)}", exc_info=True)
        return []

def extract_important_attributes(attributes):
    """
    Extract the most important attributes from the product attributes
    """
    important_keys = [
        'instanceType', 'vcpu', 'memory', 'storage', 'operatingSystem',
        'databaseEngine', 'deploymentOption', 'storageClass', 'volumeType',
        'usagetype', 'servicecode', 'location', 'servicename'
    ]
    
    return {k: v for k, v in attributes.items() if k in important_keys}

def extract_simplified_pricing(terms):
    """
    Extract simplified pricing information from the terms
    """
    pricing = {}
    
    # On-Demand pricing
    if 'OnDemand' in terms:
        on_demand = list(terms['OnDemand'].values())[0]
        price_dimensions = list(on_demand['priceDimensions'].values())[0]
        
        pricing['onDemand'] = {
            'unit': price_dimensions.get('unit', ''),
            'pricePerUnit': price_dimensions.get('pricePerUnit', {}),
            'description': price_dimensions.get('description', '')
        }
    
    # Reserved pricing (simplified)
    if 'Reserved' in terms:
        reserved = list(terms['Reserved'].values())[0]
        price_dimensions = list(reserved['priceDimensions'].values())[0]
        
        pricing['reserved'] = {
            'unit': price_dimensions.get('unit', ''),
            'pricePerUnit': price_dimensions.get('pricePerUnit', {}),
            'description': price_dimensions.get('description', '')
        }
    
    return pricing

def build_recommendations_prompt(analysis, pricing_data, cost_estimate=None):
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
        cost_summary = f"\nESTIMATED MONTHLY COST: \${cost_estimate['total_estimated_monthly_cost']:.2f} USD\n\n"
        
        # Add per-service costs
        cost_summary += "Service Cost Breakdown:\n"
        for service, service_cost in cost_estimate['service_costs'].items():
            cost_summary += f"- {service}: \${service_cost['estimated_monthly_cost']:.2f} USD\n"
        
        # Add assumptions
        cost_summary += "\nAssumptions:\n"
        for assumption in cost_estimate['assumptions'][:10]:  # Limit to top 10 assumptions
            cost_summary += f"- {assumption}\n"
        
        # Add disclaimers
        cost_summary += "\nDisclaimers:\n"
        for disclaimer in cost_estimate['disclaimers']:
            cost_summary += f"- {disclaimer}\n"
    
    prompt = {
        "anthropic_version": "bedrock-2023-05-31",
        "max_tokens": 2000,
        "messages": [
            {
                "role": "user",
                "content": f"""Based on the following infrastructure analysis, pricing information, and cost estimates, 
provide detailed optimization recommendations to improve cost efficiency, performance, security, and reliability.

Infrastructure Analysis:
{analysis}

{pricing_summary}

{cost_summary}

Please provide specific, actionable recommendations in these categories:
1. Cost optimization - Include specific instance right-sizing, reserved instances, savings plans, and storage optimizations
2. Performance improvements - Suggest architecture changes to improve performance
3. Security enhancements - Identify potential security issues and recommend solutions
4. Reliability and high availability - Recommend changes to improve system reliability
5. Architecture best practices - Suggest AWS Well-Architected Framework improvements

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


def ensure_output_bucket_exists():
    """
    Ensure the output S3 bucket exists, creating it if necessary
    """
    bucket_name = OUTPUT_BUCKET
    
    try:
        # Check if bucket exists by listing its contents
        s3.head_bucket(Bucket=bucket_name)
        logger.info(f"S3 bucket {bucket_name} already exists")
    except ClientError as e:
        error_code = e.response['Error']['Code']
        if error_code == '404' or error_code == 'NoSuchBucket':
            logger.info(f"Creating S3 bucket {bucket_name}")
            
            # Create the bucket
            try:
                region = os.environ.get('AWS_REGION', 'us-east-1')
                
                # For us-east-1, we don't need to specify LocationConstraint
                if region == 'us-east-1':
                    s3.create_bucket(Bucket=bucket_name)
                else:
                    s3.create_bucket(
                        Bucket=bucket_name,
                        CreateBucketConfiguration={
                            'LocationConstraint': region
                        }
                    )
                
                logger.info(f"S3 bucket {bucket_name} created successfully")
            except ClientError as create_error:
                logger.error(f"Error creating S3 bucket: {str(create_error)}")
                raise
        else:
            logger.error(f"Error checking S3 bucket: {str(e)}")
            raise


def store_output(output):
    """
    Store the analysis output in S3
    """
    try:
        # Create a unique file name with timestamp
        timestamp = time.strftime("%Y%m%d-%H%M%S")
        
        # Combine prefix with the output key, ensuring no double slashes
        if OUTPUT_PREFIX:
            output_key = f"{OUTPUT_PREFIX.rstrip('/')}/analysis/{timestamp}-{str(uuid.uuid4())}.json"
        else:
            output_key = f"analysis/{timestamp}-{str(uuid.uuid4())}.json"
        
        s3.put_object(
            Bucket=OUTPUT_BUCKET,
            Key=output_key,
            Body=json.dumps(output, indent=2),
            ContentType='application/json'
        )
        
        return f"s3://{OUTPUT_BUCKET}/{output_key}"
    except Exception as e:
        logger.error(f"Error storing output: {str(e)}", exc_info=True)
        raise