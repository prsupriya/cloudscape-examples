import os
import json
import base64
import tempfile
import uuid
from flask import Flask, request, jsonify
import boto3
from botocore.exceptions import NoCredentialsError, ClientError
from aws_lambda_powertools import Logger, Tracer
from aws_lambda_powertools.event_handler import BedrockAgentResolver
from aws_lambda_powertools.event_handler.openapi.params import Body, Query
from aws_lambda_powertools.utilities.typing import LambdaContext
from pydantic import BaseModel, Field
from typing import Optional, Dict, Any
from typing_extensions import Annotated
from datetime import datetime
from urllib.parse import urlparse

# Configure logging and tracing
log_level = os.environ.get('LOG_LEVEL', 'INFO')
logger = Logger(level=log_level)
tracer = Tracer()

# Initialize AWS resources
aws_region = os.environ.get('AWS_REGION', 'us-east-1')
OUTPUT_BUCKET = os.environ.get('OUTPUT_BUCKET', 'pdf-documentation-output')

# Initialize API interfaces
app = Flask(__name__)
resolver = BedrockAgentResolver()

# Define models
class PDFDocumentationOutput(BaseModel):
    """Output model for PDF documentation generation response"""
    s3_uri: str = Field(..., description="S3 URI of the generated PDF document")
    status: str = Field(..., description="Status of the operation (SUCCESS or ERROR)")
    error_message: Optional[str] = Field(None, description="Error message if status is ERROR")

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
        try:
            s3_client.head_bucket(Bucket=OUTPUT_BUCKET)
            logger.info(f"Successfully validated AWS credentials and S3 bucket: {OUTPUT_BUCKET}")
        except ClientError as e:
            error_code = e.response.get('Error', {}).get('Code', 'Unknown')
            if error_code == '404':
                logger.warning(f"S3 bucket not found: {OUTPUT_BUCKET}. Will attempt to create it.")
                s3_client.create_bucket(Bucket=OUTPUT_BUCKET)
                logger.info(f"Created S3 bucket: {OUTPUT_BUCKET}")
            elif error_code == '403':
                logger.error(f"Access denied to S3 bucket: {OUTPUT_BUCKET}. Check IAM permissions.")
                return None
            else:
                logger.error(f"Error accessing S3 bucket: {e}")
                return None
        
        return s3_client
    except NoCredentialsError:
        logger.error("AWS credentials not found. Please configure AWS credentials.")
        return None
    except ClientError as e:
        logger.error(f"Error validating AWS credentials: {e}")
        return None

# Initialize S3 client with validation
s3_client = validate_aws_credentials()

# Import PDF generation libraries
try:
    import markdown
    from weasyprint import HTML, CSS
    from weasyprint.text.fonts import FontConfiguration
    from jinja2 import Template
except ImportError as e:
    logger.warning(f"Could not import PDF generation libraries: {str(e)}")
    logger.warning("Make sure these are included in the container or Lambda layer")

# HTML template for PDF generation
HTML_TEMPLATE = """<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Documentation</title>
</head>
<body>
    <div class="header">
        <h1 class="document-title">Documentation</h1>
        <div class="document-info">
            <p>Generated on: {{ generation_date }}</p>
        </div>
    </div>
    
    <div class="document-content">
        {{ content | safe }}
    </div>
    
    {% if diagram_url %}
    <div class="architecture-diagram-section">
        <h2>Architecture Diagram</h2>
        <img src="{{ diagram_url }}" alt="Architecture Diagram" class="architecture-diagram">
    </div>
    {% endif %}
    
    <div class="footer">
        <p>Generated using PDF Documentation Generator</p>
    </div>
</body>
</html>
"""

# CSS styles for PDF generation
CSS_STYLES = '''
@page {
    margin: 2cm;
    @top-center {
        content: "Documentation";
    }
    @bottom-center {
        content: "Page " counter(page) " of " counter(pages);
    }
}
body {
    font-family: Arial, sans-serif;
    font-size: 12pt;
    line-height: 1.5;
}
h1 {
    font-size: 24pt;
    color: #2c3e50;
    border-bottom: 1px solid #eee;
    padding-bottom: 10px;
}
h2 {
    font-size: 20pt;
    color: #2c3e50;
    margin-top: 20px;
}
h3 {
    font-size: 16pt;
    color: #2c3e50;
}
pre {
    background-color: #f8f8f8;
    border: 1px solid #ddd;
    border-radius: 3px;
    padding: 10px;
    overflow-x: auto;
    font-family: "Courier New", monospace;
    font-size: 11pt;
}
code {
    font-family: "Courier New", monospace;
    background-color: #f8f8f8;
    padding: 2px 4px;
    border-radius: 3px;
    font-size: 11pt;
}
table {
    border-collapse: collapse;
    width: 100%;
    margin: 20px 0;
}
th, td {
    border: 1px solid #ddd;
    padding: 8px;
    text-align: left;
}
th {
    background-color: #f2f2f2;
    font-weight: bold;
}
img {
    max-width: 100%;
    height: auto;
}
.architecture-diagram {
    display: block;
    margin: 20px auto;
    max-width: 90%;
    border: 1px solid #ddd;
}
.table-of-contents {
    background-color: #f9f9f9;
    border: 1px solid #ddd;
    padding: 10px 20px;
    margin: 20px 0;
    border-radius: 5px;
}
.table-of-contents ul {
    list-style-type: none;
    padding-left: 20px;
}
.table-of-contents a {
    text-decoration: none;
    color: #3498db;
}
.header {
    border-bottom: 1px solid #eee;
    padding-bottom: 10px;
    margin-bottom: 20px;
}
.document-title {
    margin-top: 0;
}
.document-info {
    font-size: 0.9em;
    color: #666;
    margin-bottom: 30px;
}
.document-content {
    margin-bottom: 30px;
}
.footer {
    margin-top: 40px;
    border-top: 1px solid #eee;
    padding-top: 10px;
    text-align: center;
    font-size: 0.8em;
    color: #666;
}
'''

# Core PDF generation function - separated from API interfaces
@tracer.capture_method
def generate_pdf_core(documentation: str, link_to_architecture: Optional[str] = None) -> PDFDocumentationOutput:
    """
    Core logic for generating PDF documentation from Markdown.
    
    Args:
        documentation: Markdown content to convert to PDF
        link_to_architecture: Optional S3 URI to architecture diagram to embed
        
    Returns:
        PDFDocumentationOutput: S3 URI and status
    """
    # Check if S3 client is available
    if not s3_client:
        logger.error("Cannot generate PDF: AWS credentials or S3 bucket not available")
        return PDFDocumentationOutput(
            s3_uri="",
            status="ERROR",
            error_message="AWS credentials or S3 bucket not available"
        )
    
    try:
        logger.info("Starting PDF generation process")
        request_id = str(uuid.uuid4())
        
        # Step 1: Process the architecture diagram if provided
        diagram_data = None
        if link_to_architecture:
            try:
                logger.info(f"Retrieving architecture diagram from {link_to_architecture}")
                diagram_data = get_diagram_from_s3(link_to_architecture)
            except Exception as e:
                logger.error(f"Error retrieving diagram: {str(e)}")
                return PDFDocumentationOutput(
                    s3_uri="",
                    status="ERROR",
                    error_message=f"Error retrieving diagram: {str(e)}"
                )
        
        # Step 2: Convert Markdown to HTML
        try:
            logger.info("Converting Markdown to HTML")
            html_content = convert_markdown_to_html(documentation)
        except Exception as e:
            logger.error(f"Error converting Markdown to HTML: {str(e)}")
            return PDFDocumentationOutput(
                s3_uri="",
                status="ERROR",
                error_message=f"Error converting Markdown to HTML: {str(e)}"
            )
        
        # Step 3: Render HTML template
        try:
            logger.info("Rendering HTML template")
            rendered_html = render_html_template(html_content, diagram_data)
        except Exception as e:
            logger.error(f"Error rendering HTML template: {str(e)}")
            return PDFDocumentationOutput(
                s3_uri="",
                status="ERROR",
                error_message=f"Error rendering HTML template: {str(e)}"
            )
        
        # Step 4: Generate PDF from HTML
        try:
            logger.info("Generating PDF from HTML")
            pdf_data = generate_pdf_from_html(rendered_html)
        except Exception as e:
            logger.error(f"Error generating PDF from HTML: {str(e)}")
            return PDFDocumentationOutput(
                s3_uri="",
                status="ERROR",
                error_message=f"Error generating PDF from HTML: {str(e)}"
            )
        
        # Step 5: Upload the PDF to S3
        try:
            pdf_key = f"documentation_{request_id}.pdf"
            logger.info(f"Uploading PDF to S3 bucket {OUTPUT_BUCKET} with key {pdf_key}")
            s3_client.put_object(
                Bucket=OUTPUT_BUCKET,
                Key=pdf_key,
                Body=pdf_data,
                ContentType='application/pdf'
            )
            
            s3_uri = f"s3://{OUTPUT_BUCKET}/{pdf_key}"
            logger.info(f"PDF documentation generated and stored at {s3_uri}")
            
            return PDFDocumentationOutput(
                s3_uri=s3_uri,
                status="SUCCESS"
            )
        except Exception as e:
            logger.error(f"Error uploading PDF to S3: {str(e)}")
            return PDFDocumentationOutput(
                s3_uri="",
                status="ERROR",
                error_message=f"Error uploading PDF to S3: {str(e)}"
            )
            
    except Exception as e:
        logger.exception("Unexpected error generating PDF documentation")
        return PDFDocumentationOutput(
            s3_uri="",
            status="ERROR",
            error_message=f"Unexpected error: {str(e)}"
        )

@tracer.capture_method
def get_diagram_from_s3(s3_uri: str) -> bytes:
    """
    Get the architecture diagram from S3.
    
    Args:
        s3_uri: S3 URI of the architecture diagram
        
    Returns:
        Binary data of the architecture diagram
    """
    parsed_uri = urlparse(s3_uri)
    bucket = parsed_uri.netloc
    key = parsed_uri.path.lstrip('/')
    
    try:
        response = s3_client.get_object(Bucket=bucket, Key=key)
        return response['Body'].read()
    except Exception as e:
        logger.exception(f"Error retrieving diagram from S3: {s3_uri}")
        raise Exception(f"Failed to retrieve architecture diagram: {str(e)}")

@tracer.capture_method
def convert_markdown_to_html(markdown_content: str) -> str:
    """
    Convert Markdown content to HTML.
    
    Args:
        markdown_content: Markdown content to convert
        
    Returns:
        HTML content
    """
    # Create Markdown converter with extensions
    md = markdown.Markdown(extensions=[
        'markdown.extensions.tables',
        'markdown.extensions.fenced_code',
        'markdown.extensions.codehilite',
        'markdown.extensions.toc',
        'markdown.extensions.nl2br',
        'markdown.extensions.smarty'
    ])
    
    # Convert Markdown to HTML
    html_content = md.convert(markdown_content)
    return html_content

@tracer.capture_method
def render_html_template(html_content: str, diagram_data: Optional[bytes] = None) -> str:
    """
    Render HTML template with Markdown content and optional diagram.
    
    Args:
        html_content: HTML content converted from Markdown
        diagram_data: Optional diagram data to embed
        
    Returns:
        Rendered HTML template
    """
    try:
        # Create a Jinja2 Template directly from the string
        template = Template(HTML_TEMPLATE)
        
        # Prepare the diagram URL if provided
        diagram_url = None
        if diagram_data:
            # If diagram data is provided, embed it as a base64 data URL
            diagram_base64 = base64.b64encode(diagram_data).decode('utf-8')
            # Determine image type (assuming PNG but could be extended to check for other formats)
            image_type = "image/png"
            diagram_url = f"data:{image_type};base64,{diagram_base64}"
        
        # Get current date for the PDF metadata
        current_date = datetime.now().strftime("%Y-%m-%d")
        
        # Render the template with content and diagram
        rendered_html = template.render(
            content=html_content,
            diagram_url=diagram_url,
            generation_date=current_date
        )
        
        return rendered_html
    except Exception as e:
        logger.exception("Error rendering HTML template")
        raise Exception(f"Failed to render HTML template: {str(e)}")

@tracer.capture_method
def generate_pdf_from_html(html_content: str) -> bytes:
    """
    Generate PDF from HTML content.
    
    Args:
        html_content: HTML content to convert to PDF
        
    Returns:
        Binary data of the generated PDF
    """
    try:
        # Configure fonts
        font_config = FontConfiguration()
        
        # Define CSS for the PDF
        css = CSS(string=CSS_STYLES)
        
        # Create a temporary HTML file
        with tempfile.NamedTemporaryFile(suffix='.html', delete=False) as html_file:
            html_file_path = html_file.name
            html_file.write(html_content.encode('utf-8'))
        
        try:
            # Generate PDF
            html = HTML(filename=html_file_path)
            pdf = html.write_pdf(stylesheets=[css], font_config=font_config)
            return pdf
        finally:
            # Remove the temporary HTML file
            os.unlink(html_file_path)
    except Exception as e:
        logger.exception("Error generating PDF from HTML")
        raise Exception(f"Failed to generate PDF from HTML: {str(e)}")

# Bedrock Agent interface with Annotated type hints
@resolver.post(
    "/generatePDFDocumentation",
    description="Generate PDF documentation from Markdown content and optionally embed architecture diagrams"
)
@tracer.capture_method
def generate_pdf_documentation(
    documentation: Annotated[
        str, 
        Body(description="Documentation content in Markdown format")
    ],
    link_to_architecture: Annotated[
        Optional[str],
        Query(description="S3 URI to architecture diagram to embed")
    ] = None
) -> Annotated[bool, Body(description="Whether the PDF documentation was generated successfully")]:
    """Bedrock Agent endpoint for generating PDF documentation."""
    result = generate_pdf_core(documentation, link_to_architecture)
    
    # Return true if successful, false otherwise
    return result.status == "SUCCESS"

# Flask interface with proper error handling and improved logging
@app.route("/generatePDFDocumentation", methods=["POST"])
@tracer.capture_method
def flask_generate_pdf_documentation():
    """Flask endpoint for local development."""
    logger.info("Flask endpoint /generatePDFDocumentation called")
    try:
        data = request.json
        logger.debug(f"Received request data: {json.dumps(data)}")
        
        if not data or not isinstance(data, dict):
            logger.error("Invalid JSON payload received")
            return jsonify({
                "status": "ERROR",
                "s3_uri": "",
                "error_message": "Invalid JSON payload"
            }), 400
        
        if not data.get("documentation"):
            logger.error("Missing required parameter: documentation")
            return jsonify({
                "status": "ERROR",
                "s3_uri": "",
                "error_message": "Missing required parameter: documentation"
            }), 400
        
        # Log parameters
        logger.info(f"Processing documentation (length: {len(data['documentation'])})")
        if data.get("link_to_architecture"):
            logger.info(f"Using architecture diagram: {data['link_to_architecture']}")
        
        # Call the core function
        result = generate_pdf_core(
            documentation=data["documentation"],
            link_to_architecture=data.get("link_to_architecture")
        )
        
        # For Flask, ensure HTTP status code matches the result status
        if result.status == "ERROR":
            logger.error(f"PDF generation failed: {result.error_message}")
            return jsonify(result.dict()), 500
        
        logger.info(f"PDF generation successful: {result.s3_uri}")
        return jsonify(result.dict())
    
    except Exception as e:
        logger.exception("Unexpected error in Flask endpoint")
        return jsonify({
            "status": "ERROR",
            "s3_uri": "",
            "error_message": f"Server error: {str(e)}"
        }), 500

# Bedrock Agent detail endpoint
@resolver.get(
    "/getPDFDocumentationDetail",
    description="Get details about the generated PDF documentation"
)
@tracer.capture_method
def get_pdf_documentation_detail(
    s3_uri: Annotated[
        str,
        Query(description="S3 URI of the PDF documentation")
    ]
) -> Annotated[Dict[str, str], Body(description="Details of the PDF documentation")]:
    """Bedrock Agent endpoint for getting details about the generated PDF documentation."""
    try:
        parsed_uri = urlparse(s3_uri)
        bucket = parsed_uri.netloc
        key = parsed_uri.path.lstrip('/')
        
        # Get object metadata
        response = s3_client.head_object(Bucket=bucket, Key=key)
        
        # Return details
        return {
            "s3_uri": s3_uri,
            "content_type": response.get("ContentType", "application/pdf"),
            "size_bytes": str(response.get("ContentLength", 0)),
            "last_modified": response.get("LastModified", datetime.now()).strftime("%Y-%m-%d %H:%M:%S"),
            "status": "AVAILABLE"
        }
    except Exception as e:
        logger.exception(f"Error getting PDF documentation details: {str(e)}")
        return {
            "s3_uri": s3_uri,
            "status": "ERROR",
            "error_message": f"Error getting details: {str(e)}"
        }

# Health check endpoint
@app.route("/health", methods=["GET"])
@resolver.get(
    "/health",
    description="Check health status of the PDF documentation generator service"
)
def health_check() -> Annotated[Dict[str, str], Body(description="Health status of the service")]:
    """Health check endpoint for the service."""
    health_status = {
        "status": "healthy",
        "timestamp": datetime.now().isoformat(),
        "aws_credentials": s3_client is not None,
        "s3_bucket": OUTPUT_BUCKET
    }
    return health_status

# Lambda handler for Bedrock Agent
@logger.inject_lambda_context
@tracer.capture_lambda_handler
def lambda_handler(event: dict, context: LambdaContext) -> dict:
    """AWS Lambda handler for Bedrock Agent integration."""
    try:
        # If this is a Bedrock Agent request, use the resolver
        if "messageVersion" in event:
            logger.info("Processing Bedrock Agent request")
            return resolver.resolve(event, context)
        
        # If this is an API Gateway request
        if "requestContext" in event and "http" in event.get("requestContext", {}):
            logger.info("Processing API Gateway request")
            path = event.get("requestContext", {}).get("http", {}).get("path", "")
            method = event.get("requestContext", {}).get("http", {}).get("method", "")
            
            if path == "/health" and method == "GET":
                return {
                    "statusCode": 200,
                    "body": json.dumps(health_check())
                }
            elif path == "/generatePDFDocumentation" and method == "POST":
                try:
                    body = json.loads(event.get("body", "{}"))
                    result = generate_pdf_core(
                        documentation=body.get("documentation", ""),
                        link_to_architecture=body.get("link_to_architecture")
                    )
                    return {
                        "statusCode": 200 if result.status == "SUCCESS" else 500,
                        "body": json.dumps(result.dict())
                    }
                except Exception as e:
                    logger.exception("Error processing API Gateway request")
                    return {
                        "statusCode": 500,
                        "body": json.dumps({
                            "status": "ERROR",
                            "s3_uri": "",
                            "error_message": f"Error: {str(e)}"
                        })
                    }
            else:
                return {
                    "statusCode": 404,
                    "body": json.dumps({
                        "status": "ERROR",
                        "error_message": "Not found"
                    })
                }
        
        # Unknown event type
        logger.warning(f"Unknown event type: {json.dumps(event)}")
        return {
            "statusCode": 400,
            "body": json.dumps({
                "status": "ERROR",
                "error_message": "Unknown event type"
            })
        }
    except Exception as e:
        logger.exception("Unhandled exception in Lambda handler")
        # For Bedrock Agent
        if "messageVersion" in event:
            return {
                "messageVersion": "1.0",
                "response": {
                    "actionGroup": event.get("actionGroup", "unknown"),
                    "apiPath": event.get("apiPath", "unknown"),
                    "httpMethod": event.get("httpMethod", "unknown"),
                    "httpStatusCode": 500,
                    "responseBody": {
                        "application/json": {
                            "body": json.dumps({
                                "status": "ERROR",
                                "error_message": f"Lambda execution error: {str(e)}"
                            })
                        }
                    }
                }
            }
        # For API Gateway
        else:
            return {
                "statusCode": 500,
                "body": json.dumps({
                    "status": "ERROR",
                    "error_message": f"Lambda execution error: {str(e)}"
                })
            }

# OpenAPI schema generation
def generate_openapi_schema():
    """Generate OpenAPI schema for Bedrock Agent."""
    return resolver.get_openapi_json_schema(
        title="PDF Documentation Generator",
        description="Generate PDF documentation from Markdown content with optional architecture diagram embedding",
        version="1.0.0"
    )

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
            "The service will run but PDF uploads to S3 will not work."
        )
    
    # Generate and print schema if requested
    if os.environ.get("PRINT_SCHEMA", "").lower() == "true":
        print("Generating OpenAPI schema...")
        success = print_schema()
        if success:
            print("Schema generated successfully!")
        else:
            print("Failed to generate schema.")
    
    # Print all registered routes for debugging
    logger.info("Registered Flask routes:")
    for rule in app.url_map.iter_rules():
        logger.info(f"Route: {rule.rule} - Methods: {', '.join(rule.methods)}")
    
    # Start Flask app
    port = int(os.environ.get("PORT", 8080))
    logger.info(f"Starting PDF Documentation Generator service on port {port}")
    app.run(host="0.0.0.0", port=port, debug=True)  # Enable debug mode for more info