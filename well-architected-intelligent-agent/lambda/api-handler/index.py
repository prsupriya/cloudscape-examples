import os
import json
import boto3
import base64
from aws_lambda_powertools import Logger
from aws_lambda_powertools.utilities.typing import LambdaContext

# Initialize logger and AWS clients
logger = Logger()
s3_client = boto3.client('s3')

def parse_multipart_data(content_type, body):
    """Parse multipart form data to extract file information"""
    try:
        # Get boundary from content type
        boundary = content_type.split('boundary=')[1].encode()
        
        # Split body into parts using boundary
        parts = body.split(b'--' + boundary)
        
        files = []
        for part in parts:
            if not part.strip() or part.strip() == b'--':
                continue
                
            # Split headers and content
            try:
                headers_raw, content = part.split(b'\r\n\r\n', 1)
                headers_text = headers_raw.decode()
                
                # Check if this part contains a file
                if 'Content-Disposition: form-data;' in headers_text and 'filename=' in headers_text:
                    # Extract filename
                    filename_start = headers_text.find('filename="') + 10
                    filename_end = headers_text.find('"', filename_start)
                    filename = headers_text[filename_start:filename_end]
                    
                    # Extract content type if present
                    content_type_line = [l for l in headers_text.split('\r\n') if 'Content-Type:' in l]
                    file_content_type = content_type_line[0].split(': ')[1] if content_type_line else 'application/octet-stream'
                    
                    # Extract field name
                    name_start = headers_text.find('name="') + 6
                    name_end = headers_text.find('"', name_start)
                    field_name = headers_text[name_start:name_end]
                    
                    # Remove trailing boundary and \r\n
                    file_content = content.split(b'\r\n')[0]
                    
                    files.append({
                        'field_name': field_name,
                        'filename': filename,
                        'content_type': file_content_type,
                        'content': file_content,
                        'size': len(file_content)
                    })
                    
            except Exception as e:
                logger.error(f"Error processing part: {str(e)}")
                continue
                
        return files
    except Exception as e:
        logger.error(f"Error parsing multipart data: {str(e)}")
        raise

def handle_file_upload(event):
    """Handle file upload requests"""
    try:
        headers = event.get('headers', {})
        content_type = headers.get('content-type', '')
        
        if 'multipart/form-data' not in content_type:
            return {
                "statusCode": 400,
                "body": json.dumps({
                    "message": "Invalid content type. Expected multipart/form-data"
                })
            }
        
        # Get body and decode if needed
        body = event.get('body', '')
        if event.get('isBase64Encoded', False):
            body = base64.b64decode(body)
        elif isinstance(body, str):
            body = body.encode()
        
        # Parse multipart data
        files = parse_multipart_data(content_type, body)
        
        if not files:
            return {
                "statusCode": 400,
                "body": json.dumps({
                    "message": "No files found in request"
                })
            }
        
        # Upload each file to S3
        bucket_name = os.environ.get('S3_BUCKET_NAME')
        if not bucket_name:
            raise ValueError("S3_BUCKET_NAME environment variable not set")
        
        uploaded_files = []
        request_id = event.get('requestContext', {}).get('requestId', 'default')
        
        for file_data in files:
            # Create S3 key using original filename
            s3_key = f"uploads/{request_id}/{file_data['filename']}"
            
            # Upload to S3
            s3_client.put_object(
                Bucket=bucket_name,
                Key=s3_key,
                Body=file_data['content'],
                ContentType=file_data['content_type']
            )
            
            uploaded_files.append({
                "field_name": file_data['field_name'],
                "file_name": file_data['filename'],
                "s3_key": s3_key,
                "content_type": file_data['content_type'],
                "size": file_data['size']
            })
        
        return {
            "statusCode": 200,
            "headers": {"Content-Type": "application/json"},
            "body": json.dumps({
                "message": "Files uploaded successfully",
                "files": uploaded_files
            })
        }
    
    except Exception as e:
        logger.exception("Error processing file upload")
        return {
            "statusCode": 500,
            "body": json.dumps({
                "message": "Internal server error",
                "error": str(e)
            })
        }

def handler(event: dict, context: LambdaContext) -> dict:
    """Main Lambda handler"""
    try:
        logger.info("Received event", extra={"event": event})
        
        # Get the route and method from the event
        route_key = event.get('routeKey')
        
        if route_key == 'POST /chat':
            return handle_file_upload(event)
        else:
            return {
                "statusCode": 404,
                "body": json.dumps({
                    "message": "Route not found"
                })
            }
            
    except Exception as e:
        logger.exception("Error in handler")
        return {
            "statusCode": 500,
            "body": json.dumps({
                "message": "Internal server error",
                "error": str(e)
            })
        }
