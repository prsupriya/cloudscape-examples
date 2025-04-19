import requests
import json
import os

# API endpoint
API_ENDPOINT = "http://localhost:8080/generateArchitectureDiagram"  # Update with your actual endpoint

# Example diagram code
diagram_code = """
from diagrams import Diagram
from diagrams.aws.compute import Lambda
from diagrams.aws.storage import S3
from diagrams.aws.ml import Bedrock

# Do not define output_file or output_format variables here
# They will be injected by the service
# 
# NOTE: The Minigrammer library automatically adds the format extension
# to the filename. You don't need to include the .png extension.

# Create a diagram with title "Minigrammer Service"
with Diagram("Minigrammer Service", show=False):
    # Define the components and their relationships
    user = Bedrock("Bedrock Agent")
    function = Lambda("Diagram Generator")
    storage = S3("Diagram Storage")
    
    # Define the flow
    user >> function >> storage
    storage >> user
"""

# Request payload
payload = {
    "code": diagram_code,
    "output_format": "PNG"  # Can be PNG, SVG, or GRAPHVIZ
}

# Send request to the API
print("Sending request to", API_ENDPOINT)
print("Payload:", json.dumps(payload, indent=2))

try:
    response = requests.post(
        API_ENDPOINT,
        json=payload,
        headers={"Content-Type": "application/json"},
        timeout=30  # Increase timeout for diagram generation
    )
    
    # Process the response
    print(f"Response status code: {response.status_code}")
    
    if response.status_code == 200:
        result = response.json()
        print(f"Status: {result['status']}")
        
        if result['status'] == "SUCCESS":
            print(f"Diagram generated successfully!")
            print(f"S3 URI: {result['s3_uri']}")
        else:
            print(f"Error: {result.get('error_message', 'Unknown error')}")
    else:
        print(f"Request failed with status code {response.status_code}")
        print("Response:", response.text)
except Exception as e:
    print(f"Error during request: {str(e)}")