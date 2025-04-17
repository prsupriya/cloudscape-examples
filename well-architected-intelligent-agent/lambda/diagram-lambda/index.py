import json
import os
import sys
import logging
import boto3
from typing import Any, Dict
from botocore.exceptions import ClientError

# Configure logging
logger = logging.getLogger()
logger.setLevel(logging.DEBUG)

# Add the Python packages from the layer to the system path
sys.path.insert(0, '/opt/python')

# Set environment variables for Graphviz
os.environ['PATH'] = '/opt/bin:' + os.environ['PATH']
os.environ["LD_LIBRARY_PATH"] = "/opt/lib:/usr/lib64"

# Initialize S3 client
s3_client = boto3.client('s3')
BUCKET_NAME = os.environ.get('S3_BUCKET_NAME')  # Make sure to set this in your Lambda environment
URL_EXPIRATION = 3600  # URL expires in 1 hour

try:
    from diagrams import Diagram
    # Explicitly set the dot binary path
    DOT_BINARY = '/opt/bin/dot'
except ImportError as e:
    logger.error(f"Failed to import diagrams: {str(e)}")
    raise

def lambda_handler(event: Dict[str, Any], context: Any) -> Dict[str, Any]:
    try:
        # Debug logging
        logger.debug(f"Python path: {sys.path}")
        logger.debug(f"PATH: {os.environ['PATH']}")
        logger.debug(f"LD_LIBRARY_PATH: {os.environ['LD_LIBRARY_PATH']}")
        logger.debug(f"GVCONFIG: {os.environ['GVCONFIG']}")
        
        if not BUCKET_NAME:
            raise ValueError("BUCKET_NAME environment variable is not set")

        diagram_code = event.get('diagram_code')
        if not diagram_code:
            return {
                'statusCode': 400,
                'body': json.dumps({'error': 'No diagram code provided'})
            }

        # Create unique working directory
        work_dir = f"/tmp/diagram-{context.aws_request_id}"
        os.makedirs(work_dir, exist_ok=True)
        
        # Change to working directory
        original_dir = os.getcwd()
        os.chdir(work_dir)
        
        try:
            # Execute the diagram code
            exec(diagram_code)
            
            # Find the generated PNG file
            png_files = [f for f in os.listdir(work_dir) if f.endswith('.png')]
            if not png_files:
                raise FileNotFoundError("No PNG file was generated")
            
            png_path = os.path.join(work_dir, png_files[0])
            
            # Debug logging
            logger.debug(f"Work directory contents: {os.listdir(work_dir)}")
            logger.debug(f"PNG file exists: {os.path.exists(png_path)}")
            
            # Upload to S3
            s3_key = f"diagrams/{context.aws_request_id}.png"
            s3_client.upload_file(
                png_path,
                BUCKET_NAME,
                s3_key,
                ExtraArgs={'ContentType': 'image/png'}
            )
            
            # Generate presigned URL
            url = s3_client.generate_presigned_url(
                'get_object',
                Params={
                    'Bucket': BUCKET_NAME,
                    'Key': s3_key
                },
                ExpiresIn=URL_EXPIRATION
            )
            
            return {
                'statusCode': 200,
                'headers': {
                    'Content-Type': 'application/json'
                },
                'body': json.dumps({
                    'url': url,
                    'key': s3_key,
                    'expiresIn': URL_EXPIRATION
                })
            }
            
        finally:
            # Change back to original directory
            os.chdir(original_dir)
            
            # Cleanup
            try:
                for file in os.listdir(work_dir):
                    os.remove(os.path.join(work_dir, file))
                os.rmdir(work_dir)
            except Exception as e:
                logger.warning(f"Cleanup warning: {str(e)}")
                
    except Exception as e:
        logger.error(f"Error: {str(e)}", exc_info=True)
        return {
            'statusCode': 500,
            'body': json.dumps({
                'error': str(e)
            })
        }
    try:
        # Debug logging
        logger.debug(f"Python path: {sys.path}")
        logger.debug(f"PATH: {os.environ['PATH']}")
        logger.debug(f"LD_LIBRARY_PATH: {os.environ['LD_LIBRARY_PATH']}")
        logger.debug(f"DOT binary exists: {os.path.exists('/opt/bin/dot')}")
        
        if not BUCKET_NAME:
            raise ValueError("BUCKET_NAME environment variable is not set")

        diagram_code = event.get('diagram_code')
        if not diagram_code:
            return {
                'statusCode': 400,
                'body': json.dumps({'error': 'No diagram code provided'})
            }

        # Create tmp directory
        os.makedirs('/tmp/diagram', exist_ok=True)
        os.chmod('/tmp/diagram', 0o777)
        
        # Change to tmp directory
        os.chdir('/tmp/diagram')
        
        # Generate unique filename using request ID
        diagram_key = f"diagrams/{context.aws_request_id}.png"
        local_path = f"/tmp/diagram/{context.aws_request_id}"
        
        # Execute the diagram code
        exec(diagram_code)
        
        # Upload file to S3
        try:
            s3_client.upload_file(
                f"{local_path}.png",  # Diagram class adds .png extension
                BUCKET_NAME,
                diagram_key,
                ExtraArgs={'ContentType': 'image/png'}
            )
        except ClientError as e:
            logger.error(f"Error uploading to S3: {str(e)}")
            raise

        # Generate presigned URL
        try:
            presigned_url = s3_client.generate_presigned_url(
                'get_object',
                Params={
                    'Bucket': BUCKET_NAME,
                    'Key': diagram_key
                },
                ExpiresIn=URL_EXPIRATION
            )
        except ClientError as e:
            logger.error(f"Error generating presigned URL: {str(e)}")
            raise

        # Clean up local files
        try:
            os.remove(f"{local_path}.png")
        except OSError as e:
            logger.warning(f"Warning: Could not delete local file: {str(e)}")

        return {
            'statusCode': 200,
            'headers': {
                'Content-Type': 'application/json'
            },
            'body': json.dumps({
                'url': presigned_url,
                'expiresIn': URL_EXPIRATION,
                'key': diagram_key
            })
        }
        
    except Exception as e:
        logger.error(f"Error: {str(e)}", exc_info=True)
        return {
            'statusCode': 500,
            'body': json.dumps({'error': str(e)})
        }
