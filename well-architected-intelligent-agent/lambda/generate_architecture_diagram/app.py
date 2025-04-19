import os
import json
import tempfile
import uuid
from flask import Flask, request, jsonify
import boto3
from botocore.exceptions import NoCredentialsError, ClientError
from aws_lambda_powertools import Logger, Tracer
from aws_lambda_powertools.event_handler import BedrockAgentResolver
from aws_lambda_powertools.event_handler.exceptions import ServiceError
from aws_lambda_powertools.event_handler.openapi.params import Body, Query
from pydantic import BaseModel, Field
from typing import Literal, Optional, Dict, Any
from typing_extensions import Annotated
import re

# Configure logging and tracing
log_level = os.environ.get('LOG_LEVEL', 'INFO')
logger = Logger(level=log_level)
tracer = Tracer()

# Initialize AWS resources
aws_region = os.environ.get('AWS_REGION', 'us-east-1')
S3_BUCKET = os.environ.get('S3_BUCKET', 'minigrammer-output')

# Initialize API interfaces
app = Flask(__name__)
resolver = BedrockAgentResolver()

# Define models
class DiagramResponse(BaseModel):
    s3_uri: str = Field(
        ..., 
        description="S3 URI of the generated diagram, empty if generation failed"
    )
    status: str = Field(
        ..., 
        description="Status: SUCCESS or ERROR"
    )
    error_message: Optional[str] = Field(
        None, 
        description="Error message if generation failed"
    )

# Validate AWS credentials before starting the service
def validate_aws_credentials():
    """Validate AWS credentials are available and can access the S3 bucket."""
    try:
        # Initialize S3 client
        s3_client = boto3.client('s3', region_name=aws_region)
        
        # Try to get caller identity to show current role/user
        sts_client = boto3.client('sts', region_name=aws_region)
        identity = sts_client.get_caller_identity()
        
        logger.info(f"AWS Identity: {identity.get('Arn')}")
        logger.info(f"AWS Account: {identity.get('Account')}")
        logger.info(f"AWS User ID: {identity.get('UserId')}")
        
        # Check if bucket exists and we have access
        s3_client.head_bucket(Bucket=S3_BUCKET)
        logger.info(f"Successfully validated AWS credentials and S3 bucket: {S3_BUCKET}")
        return s3_client
    except NoCredentialsError:
        logger.error("AWS credentials not found. Please configure AWS credentials.")
        return None
    except ClientError as e:
        error_code = e.response.get('Error', {}).get('Code', 'Unknown')
        if error_code == '404':
            logger.error(f"S3 bucket not found: {S3_BUCKET}")
        elif error_code == '403':
            logger.error(f"Access denied to S3 bucket: {S3_BUCKET}. Check IAM permissions.")
        else:
            logger.error(f"Error accessing S3 bucket: {e}")
        return None

# Initialize S3 client with validation
s3_client = validate_aws_credentials()

# Core diagram generation function - separated from API interfaces
@tracer.capture_method
def generate_diagram_core(code: str, output_format: str = "png") -> DiagramResponse:
    """
    Core logic for generating architecture diagrams using Minigrammer.
    
    Args:
        code: Python code to generate the diagram
        output_format: Output format of the diagram (png, svg, or graphviz)
        
    Returns:
        DiagramResponse: S3 URI and status
    """
    # Check if S3 client is available
    if not s3_client:
        logger.error("Cannot generate diagram: AWS credentials or S3 bucket not available")
        return DiagramResponse(
            s3_uri="",
            status="ERROR",
            error_message="AWS credentials or S3 bucket not available"
        )
    
    try:
        logger.info(f"Generating diagram with output format: {output_format}")
        request_id = str(uuid.uuid4())
        
        with tempfile.TemporaryDirectory() as tmp_dir:
            # Save code to file
            code_file = os.path.join(tmp_dir, "diagram_code.py")
            with open(code_file, "w") as f:
                f.write(code)
            
            # Normalize output format
            output_format = output_format.lower()
            base_name = os.path.join(tmp_dir, "diagram")
            expected_file = f"{base_name}.{output_format}"
            
            # Modify code if needed to add parameters
            exec_code = code
            params_to_add = {}
            
            if "show=False" not in exec_code:
                params_to_add["show"] = "False"
            
            if "filename=" not in exec_code:
                params_to_add["filename"] = f"'{base_name}'"
            
            if "outformat=" not in exec_code:
                params_to_add["outformat"] = f"'{output_format}'"
            
            # Only modify the code if we need to add parameters
            if params_to_add:
                # Find the Diagram constructor
                diagram_pattern = r'with\s+Diagram\s*\('
                match = re.search(diagram_pattern, exec_code)
                if match:
                    start_pos = match.end()
                    
                    # Extract existing parameters
                    open_parens = 1
                    end_pos = start_pos
                    while open_parens > 0 and end_pos < len(exec_code):
                        if exec_code[end_pos] == '(':
                            open_parens += 1
                        elif exec_code[end_pos] == ')':
                            open_parens -= 1
                        end_pos += 1
                    
                    original_args = exec_code[start_pos:end_pos-1].strip()
                    
                    # Add our parameters
                    new_args = original_args
                    for key, value in params_to_add.items():
                        new_args += f", {key}={value}"
                    
                    exec_code = exec_code[:start_pos] + new_args + exec_code[end_pos-1:]
            
            logger.info(f"Executing diagram code...")
            try:
                # Create a safe execution namespace
                exec_globals = {
                    '__builtins__': __builtins__,
                    '__name__': '__main__'
                }
                exec(exec_code, exec_globals)
            except Exception as e:
                logger.exception(f"Error executing diagram code: {str(e)}")
                return DiagramResponse(
                    s3_uri="",
                    status="ERROR",
                    error_message=f"Error executing diagram code: {str(e)}"
                )
            
            # Find the generated file
            files_in_dir = os.listdir(tmp_dir)
            logger.debug(f"Files in directory after execution: {files_in_dir}")
            
            actual_file = None
            for file in files_in_dir:
                if file.startswith("diagram") and file.endswith(f".{output_format}"):
                    actual_file = os.path.join(tmp_dir, file)
                    break
            
            if not actual_file:
                logger.error("Diagram generation failed, output file not found")
                return DiagramResponse(
                    s3_uri="",
                    status="ERROR",
                    error_message="Diagram generation failed, output file not found"
                )
            
            # Upload to S3
            try:
                s3_key = f"diagrams/{request_id}.{output_format}"
                logger.info(f"Uploading file to S3: {actual_file} -> s3://{S3_BUCKET}/{s3_key}")
                s3_client.upload_file(actual_file, S3_BUCKET, s3_key)
                
                s3_uri = f"s3://{S3_BUCKET}/{s3_key}"
                logger.info(f"Successfully generated diagram: {s3_uri}")
                
                return DiagramResponse(
                    s3_uri=s3_uri,
                    status="SUCCESS"
                )
            except (NoCredentialsError, ClientError) as e:
                logger.exception(f"Failed to upload file to S3: {str(e)}")
                return DiagramResponse(
                    s3_uri="",
                    status="ERROR",
                    error_message=f"Failed to upload diagram to S3: {str(e)}"
                )
            
    except Exception as e:
        logger.exception("Error generating diagram")
        return DiagramResponse(
            s3_uri="",
            status="ERROR",
            error_message=f"Unexpected error: {str(e)}"
        )

# Bedrock Agent interface with Annotated type hints
@resolver.post(
    "/generateArchitectureDiagram",
    description="Generate architecture diagrams using Python diagrams library code. Import components and use '>>' to define relationships."
)
@tracer.capture_method
def generate_architecture_diagram(
    code: Annotated[
        str, 
        Body(description="Python code using diagrams library with 'with Diagram():' syntax. Define components and relationships.")
    ],
    output_format: Annotated[
        Literal["PNG", "SVG", "GRAPHVIZ"],
        Query(description="Output format: PNG (default), SVG (vector), or GRAPHVIZ (DOT format)")
    ] = "PNG"
) -> Annotated[
    DiagramResponse, 
    Body(description="Response containing the S3 URI of the generated diagram or error details")
]:
    """Bedrock Agent endpoint for generating architecture diagrams."""
    result = generate_diagram_core(code, output_format.lower())
    return result

# Flask interface with proper error handling
@app.route("/generateArchitectureDiagram", methods=["POST"])
@tracer.capture_method
def flask_generate_architecture_diagram():
    """Flask endpoint for local development."""
    try:
        data = request.json
        
        if not data or not isinstance(data, dict):
            return jsonify({
                "status": "ERROR",
                "error_message": "Invalid JSON payload"
            }), 400
        
        if not data.get("code"):
            return jsonify({
                "status": "ERROR",
                "error_message": "Missing required parameter: code"
            }), 400
        
        output_format = data.get("output_format", "PNG")
        if output_format not in ["PNG", "SVG", "GRAPHVIZ"]:
            return jsonify({
                "status": "ERROR",
                "error_message": "Invalid output format. Must be PNG, SVG, or GRAPHVIZ"
            }), 400
        
        # Call the core function
        result = generate_diagram_core(data["code"], output_format.lower())
        
        # For Flask, ensure HTTP status code matches the result status
        if result.status == "ERROR":
            return jsonify(result.model_dump()), 500
        
        return jsonify(result.model_dump())
    
    except Exception as e:
        logger.exception("Unexpected error in Flask endpoint")
        return jsonify({
            "status": "ERROR",
            "s3_uri": "",
            "error_message": f"Server error: {str(e)}"
        }), 500

# Lambda handler for Bedrock Agent
@logger.inject_lambda_context
@tracer.capture_lambda_handler
def lambda_handler(event, context):
    """AWS Lambda handler for Bedrock Agent integration."""
    try:
        return resolver.resolve(event, context)
    except Exception as e:
        logger.exception("Unhandled exception in Lambda handler")
        # Return a formatted error response that Bedrock can understand
        return {
            "messageVersion": "1.0",
            "response": {
                "actionGroup": event.get("actionGroup", "unknown"),
                "apiPath": event.get("apiPath", "unknown"),
                "httpMethod": event.get("httpMethod", "unknown"),
                "httpStatusCode": 500,
                "responseBody": {
                    "applicationResponse": json.dumps({
                        "status": "ERROR",
                        "s3_uri": "",
                        "error_message": f"Lambda execution error: {str(e)}"
                    })
                }
            }
        }

# OpenAPI schema generation
def generate_openapi_schema():
    """Generate OpenAPI schema for Bedrock Agent."""
    return resolver.get_openapi_json_schema(
        title="Minigrammer Diagram Generator",
        description="Generate architecture diagrams using Python diagrams library. Creates visual diagrams saved to S3.",
        version="1.0.0"
    )

# Health check endpoint
@app.route("/health", methods=["GET"])
def health_check():
    """Health check endpoint for the service."""
    health_status = {
        "status": "healthy",
        "aws_credentials": s3_client is not None,
        "s3_bucket": S3_BUCKET
    }
    return jsonify(health_status)

# Utility to print the schema for development purposes
def print_schema():
    """Print the OpenAPI schema to console."""
    try:
        schema = generate_openapi_schema()
        print(json.dumps(json.loads(schema), indent=2))
        return True
    except Exception as e:
        print(f"Error generating schema: {str(e)}")
        return False

# Run as Flask app for local development
if __name__ == "__main__":
    # Check AWS credentials before starting
    if not s3_client:
        logger.warning(
            "WARNING: AWS credentials validation failed. "
            "The service will run but diagram uploads to S3 will not work."
        )
    
    # Generate and print schema if requested
    if os.environ.get("PRINT_SCHEMA", "").lower() == "true":
        print("Generating OpenAPI schema...")
        success = print_schema()
        if success:
            print("Schema generated successfully!")
        else:
            print("Failed to generate schema.")
    
    # Start Flask app
    port = int(os.environ.get("PORT", 8080))
    logger.info(f"Starting Minigrammer service on port {port}")
    app.run(host="0.0.0.0", port=port, debug=False)