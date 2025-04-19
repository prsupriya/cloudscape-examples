#!/bin/bash
# This script tests the PDF Documentation Generator API with the sample document

# Default values
API_ENDPOINT="http://localhost:8080"
DIAGRAM_URI=""
VERBOSE=false

print_usage() {
  echo "Usage: $0 [-e API_ENDPOINT] [-d DIAGRAM_URI] [-v]"
  echo "  -e API_ENDPOINT : API endpoint URL (default: http://localhost:8080)"
  echo "  -d DIAGRAM_URI  : S3 URI to an architecture diagram (optional)"
  echo "  -v              : Enable verbose output"
  exit 1
}

while [[ $# -gt 0 ]]; do
  case $1 in
    -e) API_ENDPOINT="$2"; shift 2 ;;
    -d) DIAGRAM_URI="$2"; shift 2 ;;
    -v) VERBOSE=true; shift ;;
    *) echo "Unknown option: $1"; print_usage ;;
  esac
done

echo "Testing PDF Documentation Generator API"
echo "-------------------------------------"
echo "API Endpoint: $API_ENDPOINT"
if [ ! -z "$DIAGRAM_URI" ]; then
  echo "Using diagram: $DIAGRAM_URI"
fi
echo

# Check if the API is running
echo "Checking API health..."
HEALTH_RESPONSE=$(curl -s "$API_ENDPOINT/health")

if [ $? -ne 0 ]; then
  echo "Error: Could not connect to API endpoint. Make sure the server is running."
  exit 1
fi

echo "API health response: $HEALTH_RESPONSE"
echo

# Build the command to test the API
COMMAND="python3 client_example.py -m sample.html -e $API_ENDPOINT"

if [ ! -z "$DIAGRAM_URI" ]; then
  COMMAND="$COMMAND -a $DIAGRAM_URI"
fi

if [ "$VERBOSE" = true ]; then
  COMMAND="$COMMAND -v"
fi

# Run the test
echo "Running test with sample document..."
echo "> $COMMAND"
echo

eval $COMMAND

echo
echo "Test complete."