import os
import json
import base64
from aws_lambda_powertools import Logger, Tracer
from aws_lambda_powertools.event_handler import APIGatewayRestResolver
from aws_lambda_powertools.utilities.typing import LambdaContext
import boto3

logger = Logger()
tracer = Tracer()
app = APIGatewayRestResolver()
s3_client = boto3.client('s3')

def parse_multipart_form_data(content_type: str, body: bytes) -> dict:
    """Parse multipart form data using a simple approach"""
    try:
        # Get boundary from content type
        boundary = content_type.split('boundary=')[1].encode()
        logger.info("Found boundary", extra={"boundary": boundary.decode()})

        # Split body into parts using boundary
        parts = body.split(b'--' + boundary)
        logger.info("Split parts", extra={"num_parts": len(parts)})

        form_data = {}
        
        # Process each part
        for part in parts:
            # Skip empty parts and boundary end marker
            if not part.strip() or part.strip() == b'--':
                continue

            logger.info("Processing part", extra={"part_size": len(part)})
            
            try:
                # Split headers and content
                headers_raw, content = part.split(b'\r\n\r\n', 1)
                headers_text = headers_raw.decode()
                logger.info("Part headers", extra={"headers": headers_text})

                # Parse Content-Disposition
                if 'Content-Disposition: form-data;' not in headers_text:
                    continue

                # Get field name
                name_start = headers_text.find('name="') + 6
                name_end = headers_text.find('"', name_start)
                field_name = headers_text[name_start:name_end]

                # Check if it's a file
                is_file = 'filename="' in headers_text
                if is_file:
                    filename_start = headers_text.find('filename="') + 10
                    filename_end = headers_text.find('"', filename_start)
                    filename = headers_text[filename_start:filename_end]

                    # Get content type if present
                    content_type_line = [l for l in headers_text.split('\r\n') if 'Content-Type:' in l]
                    file_content_type = content_type_line[0].split(': ')[1] if content_type_line else 'application/octet-stream'

                    # Remove trailing boundary and \r\n
                    file_content = content.split(b'\r\n')[0]

                    form_data[field_name] = {
                        'filename': filename,
                        'content_type': file_content_type,
                        'content': file_content
                    }
                    logger.info("Processed file field", extra={
                        "field_name": field_name,
                        "filename": filename,
                        "content_type": file_content_type,
                        "content_size": len(file_content)
                    })
                else:
                    # Regular form field
                    field_value = content.split(b'\r\n')[0].decode()
                    form_data[field_name] = field_value
                    logger.info("Processed form field", extra={
                        "field_name": field_name,
                        "value_length": len(field_value)
                    })

            except Exception as e:
                logger.error(f"Error processing part: {str(e)}", extra={
                    "part_excerpt": part[:100].decode(errors='ignore')
                })

        return form_data

    except Exception as e:
        logger.error(f"Error parsing multipart data: {str(e)}")
        raise

@logger.inject_lambda_context
@tracer.capture_lambda_handler
def handler(event: dict, context: LambdaContext) -> dict:
    try:
        # Log incoming event
        logger.info("Received event", extra={
            "headers": event.get("headers", {}),
            "isBase64Encoded": event.get("isBase64Encoded", False)
        })

        body = event.get('body', '')
        headers = event.get('headers', {})
        content_type = headers.get('content-type', '')

        if not content_type.startswith('multipart/form-data'):
            return {
                "statusCode": 400,
                "body": json.dumps({
                    "message": "Invalid content type. Expected multipart/form-data",
                    "received": content_type
                })
            }

        # Decode base64 body
        if event.get('isBase64Encoded', False):
            try:
                body_bytes = base64.b64decode(body)
                logger.info("Decoded base64 body", extra={
                    "decoded_size": len(body_bytes),
                    "excerpt": body_bytes[:100].decode(errors='ignore')
                })
            except Exception as e:
                logger.error(f"Base64 decode error: {str(e)}")
                return {
                    "statusCode": 400,
                    "body": json.dumps({
                        "message": "Invalid base64 encoding",
                        "error": str(e)
                    })
                }
        else:
            body_bytes = body.encode() if isinstance(body, str) else body

        # Parse multipart form data
        form_data = parse_multipart_form_data(content_type, body_bytes)
        
        # Process files
        files = {k: v for k, v in form_data.items() if isinstance(v, dict) and 'filename' in v}
        
        if files:
            uploaded_files = []
            bucket_name = os.environ.get('S3_BUCKET_NAME')
            
            if not bucket_name:
                raise ValueError("S3_BUCKET_NAME environment variable not set")

            for field_name, file_data in files.items():
                s3_key = f"uploads/{context.aws_request_id}/{file_data['filename']}"
                
                s3_client.put_object(
                    Bucket=bucket_name,
                    Key=s3_key,
                    Body=file_data['content'],
                    ContentType=file_data['content_type']
                )
                
                uploaded_files.append({
                    "field_name": field_name,
                    "file_name": file_data['filename'],
                    "s3_key": s3_key,
                    "content_type": file_data['content_type'],
                    "size": len(file_data['content'])
                })

            response_data = {
                "message": "Files uploaded successfully",
                "files": uploaded_files
            }
        else:
            # Get non-file fields
            form_fields = {k: v for k, v in form_data.items() if isinstance(v, str)}
            
            response_data = {
                "message": "No files received",
                "form_fields": form_fields
            }

        return {
            "statusCode": 200,
            "headers": {
                "Content-Type": "application/json"
            },
            "body": json.dumps(response_data)
        }

    except Exception as e:
        logger.exception("Unhandled error")
        return {
            "statusCode": 500,
            "body": json.dumps({
                "message": "Internal server error",
                "error": str(e)
            })
        }
