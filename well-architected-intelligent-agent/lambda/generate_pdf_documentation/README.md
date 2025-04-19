# PDF Documentation Generator

A service that converts Markdown documentation to PDF and optionally embeds architecture diagrams. This Lambda-based service can be used as a standalone API or integrated with Amazon Bedrock Agents.

## Features

- Convert Markdown to well-formatted PDF documents
- Support for standard Markdown syntax (headings, lists, code blocks, tables, etc.)
- Embed architecture diagrams from S3 into the generated PDF
- Store generated PDFs in S3 with unique identifiers
- Amazon Bedrock Agent integration through OpenAPI schema
- Standalone API access

## Requirements

- Python 3.9+
- AWS account with permissions for Lambda and S3
- Dependencies listed in `requirements.txt`

## Deployment Options

### Using Docker

1. Build the Docker image:
   ```
   docker build -t pdf-documentation-generator .
   ```

2. Run locally for testing:
   ```
   docker run -p 8080:8080 -e AWS_ACCESS_KEY_ID=your-key -e AWS_SECRET_ACCESS_KEY=your-secret -e AWS_REGION=us-east-1 -e OUTPUT_BUCKET=your-bucket pdf-documentation-generator
   ```

3. Deploy to AWS Lambda:
   ```
   aws ecr create-repository --repository-name pdf-documentation-generator
   aws ecr get-login-password | docker login --username AWS --password-stdin your-account-id.dkr.ecr.region.amazonaws.com
   docker tag pdf-documentation-generator:latest your-account-id.dkr.ecr.region.amazonaws.com/pdf-documentation-generator:latest
   docker push your-account-id.dkr.ecr.region.amazonaws.com/pdf-documentation-generator:latest
   ```

### Using AWS CDK (preferred)

See the included CDK code for deploying the service as a Lambda function with Amazon Bedrock Agent integration.

## Environment Variables

- `OUTPUT_BUCKET` - S3 bucket for storing generated PDFs (default: "pdf-documentation-output")
- `AWS_REGION` - AWS region (default: "us-east-1")
- `LOG_LEVEL` - Logging level (default: "INFO")
- `PORT` - Port for local Flask server (default: 8080)
- `PRINT_SCHEMA` - Set to "true" to print OpenAPI schema on startup

## Local Development

1. Install dependencies:
   ```
   pip install -r requirements.txt
   ```

2. Run the Flask server:
   ```
   python app.py
   ```

3. Generate OpenAPI schema for Bedrock Agent:
   ```
   PRINT_SCHEMA=true python app.py
   ```

4. Test with the provided client example:
   ```
   python client_example.py -m your_markdown_file.md -a s3://your-bucket/diagram.png
   ```

## API Endpoints

### `/generatePDFDocumentation` (POST)

Generate a PDF from Markdown content with an optional architecture diagram.

**Request Parameters:**
- `documentation` (required): Markdown content
- `link_to_architecture` (optional): S3 URI to an architecture diagram

**Response:**
```json
{
  "s3_uri": "s3://your-bucket/documentation_uuid.pdf",
  "status": "SUCCESS"
}
```

### `/getPDFDocumentationDetail` (GET)

Get details about a previously generated PDF.

**Query Parameters:**
- `s3_uri` (required): S3 URI of the PDF

**Response:**
```json
{
  "s3_uri": "s3://your-bucket/documentation_uuid.pdf",
  "content_type": "application/pdf",
  "size_bytes": "123456",
  "last_modified": "2025-04-18 12:34:56",
  "status": "AVAILABLE"
}
```

### `/health` (GET)

Health check endpoint.

**Response:**
```json
{
  "status": "healthy",
  "timestamp": "2025-04-18T12:34:56.789Z",
  "aws_credentials": true,
  "s3_bucket": "pdf-documentation-output"
}
```

## Amazon Bedrock Agent Integration

To integrate with Amazon Bedrock Agents:

1. Generate the OpenAPI schema using `PRINT_SCHEMA=true python app.py`
2. Create a new Bedrock Agent
3. Create an Action Group using the generated schema
4. Configure the Lambda function as the executor for the Action Group

## Notes on PDF Generation

This service uses WeasyPrint for PDF generation, which requires system-level dependencies. These are included in the provided Dockerfile. If you're deploying without Docker, ensure these dependencies are installed in your Lambda layer.

## Example Client Usage

```bash
# Generate a PDF from a Markdown file
python client_example.py -m documentation.md

# Generate a PDF with an embedded architecture diagram
python client_example.py -m documentation.md -a s3://your-bucket/diagram.png

# Use a custom endpoint
python client_example.py -m documentation.md -e http://your-api-endpoint

# Enable verbose mode
python client_example.py -m documentation.md -v

# Enable debug mode
python client_example.py -m documentation.md -d
```