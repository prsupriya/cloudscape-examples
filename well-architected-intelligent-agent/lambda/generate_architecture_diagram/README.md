# Minigrammer Diagram Generator Service

This service provides an API for generating architecture diagrams using the [Minigrammer/Diagrams](https://diagrams.mingrammer.com/) Python library. It can be deployed as a containerized service on AWS Lambda or ECS.

## Features

- RESTful API for generating architecture diagrams
- Support for PNG, SVG, and GRAPHVIZ output formats
- Integration with Amazon Bedrock Agents
- Automatic storage of generated diagrams in S3
- AWS Lambda PowerTools for logging, tracing, and observability

## Architecture

The service follows this basic workflow:

1. Receive a request with Python code and output format
2. Execute the code in a secure environment to generate a diagram
3. Upload the generated diagram to an S3 bucket
4. Return the S3 URI and status to the client

## Prerequisites

- Python 3.7+
- Docker
- AWS account with appropriate permissions
- S3 bucket for storing generated diagrams
- (Optional) Amazon Bedrock for agent integration

## Getting Started

### Local Development

1. Install dependencies:
   ```
   pip install -r requirements.txt awscli
   ```

2. Dynamically retrieve AWS credentials using AWS STS:
   ```bash
   # Configure your AWS CLI profile if not already done
   aws configure

   # For the default profile
   export AWS_ACCESS_KEY_ID=$(aws sts get-session-token --query 'Credentials.AccessKeyId' --output text)
   export AWS_SECRET_ACCESS_KEY=$(aws sts get-session-token --query 'Credentials.SecretAccessKey' --output text)
   export AWS_SESSION_TOKEN=$(aws sts get-session-token --query 'Credentials.SessionToken' --output text)
   
   # OR for a specific profile
   export AWS_ACCESS_KEY_ID=$(aws sts get-session-token --profile your-profile --query 'Credentials.AccessKeyId' --output text)
   export AWS_SECRET_ACCESS_KEY=$(aws sts get-session-token --profile your-profile --query 'Credentials.SecretAccessKey' --output text)
   export AWS_SESSION_TOKEN=$(aws sts get-session-token --profile your-profile --query 'Credentials.SessionToken' --output text)
   
   # For assuming a specific role (common for cross-account access)
   export AWS_ACCESS_KEY_ID=$(aws sts assume-role --role-arn arn:aws:iam::123456789012:role/YourRole --role-session-name local-dev --query 'Credentials.AccessKeyId' --output text)
   export AWS_SECRET_ACCESS_KEY=$(aws sts assume-role --role-arn arn:aws:iam::123456789012:role/YourRole --role-session-name local-dev --query 'Credentials.SecretAccessKey' --output text)
   export AWS_SESSION_TOKEN=$(aws sts assume-role --role-arn arn:aws:iam::123456789012:role/YourRole --role-session-name local-dev --query 'Credentials.SessionToken' --output text)
   ```

3. Set the required environment variables:
   ```bash
   export S3_BUCKET=your-s3-bucket-name
   export LOG_LEVEL=INFO
   ```

4. Run the application locally:
   ```
   python app.py
   ```

5. The API will be available at `http://localhost:8080`

> **Note**: For Windows users, use `set` instead of `export` or use a script to set environment variables.

### Building and Running with Docker

1. Build the Docker image:
   ```
   docker build -t minigrammer-service .
   ```

2. Dynamically retrieve AWS credentials using AWS STS and run the container:
   ```bash
   # For the default profile
   docker run -p 8080:8080 \
     -e S3_BUCKET=your-bucket-name \
     -e AWS_ACCESS_KEY_ID=$(aws sts get-session-token --query 'Credentials.AccessKeyId' --output text) \
     -e AWS_SECRET_ACCESS_KEY=$(aws sts get-session-token --query 'Credentials.SecretAccessKey' --output text) \
     -e AWS_SESSION_TOKEN=$(aws sts get-session-token --query 'Credentials.SessionToken' --output text) \
     minigrammer-service
   ```

## Example

Check the `examples` directory for sample code showing how to:
1. Generate a diagram (`examples/aws_web_service_diagram.py`)
2. Use the API from a client application (`examples/client_example.py`)

## Amazon Bedrock Integration

This service is designed to work with Amazon Bedrock Agents. The OpenAPI schema for Bedrock integration can be generated using:

```python
from app import generate_openapi_schema
schema = generate_openapi_schema()
print(schema)
```

Save the output to a file (e.g., `openapi_schema.json`) and use it when creating your Bedrock Agent.

## Environment Variables

- `S3_BUCKET`: Name of the S3 bucket to store diagrams (required)
- `PORT`: Port to run the Flask application (default: 8080)
- `LOG_LEVEL`: Logging level (default: INFO)
- `AWS_ACCESS_KEY_ID`: AWS access key for S3 operations
- `AWS_SECRET_ACCESS_KEY`: AWS secret key for S3 operations
- `AWS_SESSION_TOKEN`: AWS session token for temporary credentials (when using STS)
- `AWS_REGION`: AWS region to use (default: us-east-1)

## Security Considerations

### Using Temporary Credentials with Limited Permissions

For enhanced security, especially during local development, create a dedicated IAM role with least-privilege permissions:

1. Create an IAM policy with only the required permissions:

```json
{
  "Version": "2012-10-17",
  "Statement": [
    {
      "Effect": "Allow",
      "Action": [
        "s3:PutObject",
        "s3:GetObject"
      ],
      "Resource": "arn:aws:s3:::your-bucket-name/*"
    },
    {
      "Effect": "Allow",
      "Action": [
        "s3:ListBucket"
      ],
      "Resource": "arn:aws:s3:::your-bucket-name"
    }
  ]
}
```

2. Create an IAM role with this policy and configure it for assume-role access.

3. Use AWS STS to assume this role with short-lived credentials:

```bash
# Get temporary credentials assuming a specific role
creds=$(aws sts assume-role \
  --role-arn arn:aws:iam::123456789012:role/MinigrammerServiceRole \
  --role-session-name minigrammer-dev \
  --duration-seconds 3600)

# Extract and export the credentials
export AWS_ACCESS_KEY_ID=$(echo $creds | jq -r .Credentials.AccessKeyId)
export AWS_SECRET_ACCESS_KEY=$(echo $creds | jq -r .Credentials.SecretAccessKey)
export AWS_SESSION_TOKEN=$(echo $creds | jq -r .Credentials.SessionToken)
```

This approach ensures that:
- Credentials are temporary (expire after the specified duration)
- Permissions are limited to only what the service needs
- The service cannot access other AWS resources outside its scope

## License

[MIT License](../../LICENSE)