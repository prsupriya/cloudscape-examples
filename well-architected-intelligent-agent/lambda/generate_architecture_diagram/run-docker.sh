#!/bin/bash
# This script builds and runs the Docker container with AWS credentials

# Parse command-line arguments
PROFILE="default"
ROLE_ARN=""
BUCKET_NAME=""
REBUILD=false
PORT=8080

print_usage() {
  echo "Usage: $0 -b BUCKET_NAME [-p PROFILE] [-r ROLE_ARN] [-P PORT] [--rebuild]"
  echo "  -b BUCKET_NAME  : S3 bucket name for storing diagrams (required)"
  echo "  -p PROFILE      : AWS CLI profile to use (default: default)"
  echo "  -r ROLE_ARN     : IAM role ARN to assume (optional)"
  echo "  -P PORT         : Port to expose (default: 8080)"
  echo "  --rebuild       : Force rebuild of the Docker image"
  exit 1
}

while [[ $# -gt 0 ]]; do
  case $1 in
    -p) PROFILE="$2"; shift 2 ;;
    -r) ROLE_ARN="$2"; shift 2 ;;
    -b) BUCKET_NAME="$2"; shift 2 ;;
    -P) PORT="$2"; shift 2 ;;
    --rebuild) REBUILD=true; shift ;;
    *) echo "Unknown option: $1"; print_usage ;;
  esac
done

# Check if bucket name is provided
if [ -z "$BUCKET_NAME" ]; then
  echo "Error: S3 bucket name (-b) is required"
  print_usage
fi

echo "Starting Minigrammer Docker Environment"
echo "------------------------------------"
echo "AWS Profile: $PROFILE"
echo "S3 Bucket: $BUCKET_NAME"
echo "Port: $PORT"
if [ ! -z "$ROLE_ARN" ]; then
  echo "IAM Role: $ROLE_ARN"
fi
echo

# Build the Docker image if needed
if [ "$REBUILD" = true ] || [ -z "$(docker images -q minigrammer-service)" ]; then
  echo "Building Docker image..."
  docker build -t minigrammer-service .
fi

# Get AWS credentials
if [ -z "$ROLE_ARN" ]; then
  echo "Getting session token from AWS STS..."
  CREDS=$(aws sts get-session-token --profile $PROFILE)
else
  echo "Assuming role $ROLE_ARN..."
  CREDS=$(aws sts assume-role --role-arn $ROLE_ARN --role-session-name minigrammer-docker --profile $PROFILE)
fi

# Check if the AWS command succeeded
if [ $? -ne 0 ]; then
  echo "Error retrieving AWS credentials. Check your AWS configuration and try again."
  exit 1
fi

# Extract credentials
AWS_ACCESS_KEY_ID=$(echo $CREDS | jq -r .Credentials.AccessKeyId)
AWS_SECRET_ACCESS_KEY=$(echo $CREDS | jq -r .Credentials.SecretAccessKey)
AWS_SESSION_TOKEN=$(echo $CREDS | jq -r .Credentials.SessionToken)

# Validate credentials were obtained correctly
if [ -z "$AWS_ACCESS_KEY_ID" ] || [ "$AWS_ACCESS_KEY_ID" == "null" ]; then
  echo "Error: Failed to extract AWS credentials. Make sure jq is installed and your AWS config is correct."
  exit 1
fi

echo "AWS credentials successfully obtained. Expiration: $(echo $CREDS | jq -r .Credentials.Expiration)"
echo "Starting Docker container..."

# Run the Docker container
docker run -p $PORT:8080 \
  -e S3_BUCKET=$BUCKET_NAME \
  -e AWS_ACCESS_KEY_ID=$AWS_ACCESS_KEY_ID \
  -e AWS_SECRET_ACCESS_KEY=$AWS_SECRET_ACCESS_KEY \
  -e AWS_SESSION_TOKEN=$AWS_SESSION_TOKEN \
  -e LOG_LEVEL=INFO \
  minigrammer-service

# Note: The container will remain running in the foreground
# Press Ctrl+C to stop it