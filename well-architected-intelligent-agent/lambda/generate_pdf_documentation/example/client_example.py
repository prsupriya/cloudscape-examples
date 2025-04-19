#!/usr/bin/env python3
import requests
import json
import os
import argparse
import sys

def read_file(file_path):
    """Read content from a file"""
    try:
        with open(file_path, 'r', encoding='utf-8') as file:
            return file.read()
    except Exception as e:
        print(f"Error reading file {file_path}: {str(e)}")
        sys.exit(1)

def main():
    # Parse command line arguments
    parser = argparse.ArgumentParser(description="Test the PDF Documentation Generator API")
    parser.add_argument("-m", "--markdown", required=True, help="Path to Markdown file")
    parser.add_argument("-a", "--architecture", help="S3 URI of architecture diagram to embed (or path to file containing the URI)")
    parser.add_argument("-e", "--endpoint", default="http://localhost:8080", help="API endpoint base URL")
    parser.add_argument("-v", "--verbose", action="store_true", help="Show verbose output")
    parser.add_argument("-d", "--debug", action="store_true", help="Show debug information")
    
    args = parser.parse_args()
    
    # API endpoint
    api_endpoint = f"{args.endpoint}/generatePDFDocumentation"
    
    # Read Markdown content
    markdown_content = read_file(args.markdown)
    
    # Process architecture diagram URI if provided
    architecture_uri = None
    if args.architecture:
        # Check if it's a file containing the URI
        if os.path.isfile(args.architecture):
            architecture_uri = read_file(args.architecture).strip()
        else:
            # Assume it's the URI itself
            architecture_uri = args.architecture
    
    # Request payload
    payload = {
        "documentation": markdown_content
    }
    
    if architecture_uri:
        payload["link_to_architecture"] = architecture_uri
    
    # Print request details if verbose
    if args.verbose or args.debug:
        print("API Endpoint:", api_endpoint)
        print("Markdown File:", args.markdown)
        print("Markdown Length:", len(markdown_content), "characters")
        if architecture_uri:
            print("Architecture URI:", architecture_uri)
        print("\nSending request...")
    else:
        print(f"Sending request to {api_endpoint}...")
    
    # If debug mode, check if the server is reachable
    if args.debug:
        try:
            health_response = requests.get(f"{args.endpoint}/health")
            print(f"Health check status: {health_response.status_code}")
            if health_response.status_code == 200:
                print("Server is healthy")
            else:
                print("Server returned unhealthy status")
        except requests.exceptions.ConnectionError:
            print("ERROR: Cannot connect to server. Is it running?")
            return
    
    # Send request to the API
    try:
        if args.debug:
            print("\nRequest Headers:")
            headers = {"Content-Type": "application/json"}
            print(json.dumps(headers, indent=2))
            
            print("\nRequest Payload:")
            print(json.dumps({"documentation": f"[{len(markdown_content)} chars]", 
                            "link_to_architecture": architecture_uri}, indent=2))
        
        response = requests.post(
            api_endpoint,
            json=payload,
            headers={"Content-Type": "application/json"},
            timeout=60  # Increase timeout for PDF generation
        )
        
        # Process the response
        print(f"\nResponse status code: {response.status_code}")
        
        if args.debug:
            print("Response Headers:")
            print(json.dumps(dict(response.headers), indent=2))
        
        if response.status_code == 200:
            try:
                result = response.json()
                print(json.dumps(result, indent=2))
                
                if result.get('status') == "SUCCESS":
                    print("\n✅ PDF documentation generated successfully!")
                    print(f"S3 URI: {result.get('s3_uri')}")
                else:
                    print(f"\n❌ Error: {result.get('error_message', 'Unknown error')}")
            except json.JSONDecodeError:
                print("\n❌ Error: Response is not valid JSON")
                print(response.text)
        else:
            print(f"\n❌ Request failed with status code {response.status_code}")
            print("Response:", response.text)
            
            if args.debug and response.status_code == 404:
                print("\nDEBUG: Endpoint not found (404). Available endpoints may include:")
                print("- /generatePDFDocumentation")
                print("- /health")
                print("- /getPDFDocumentationDetail")
                print("\nCheck the server logs for registered routes.")
    except Exception as e:
        print(f"\n❌ Error during request: {str(e)}")
        if args.debug:
            import traceback
            print("\nTraceback:")
            traceback.print_exc()

if __name__ == "__main__":
    main()