import json
import os
import boto3
from diagrams import Diagram

# Set environment variables for Graphviz
os.environ['PATH'] = os.environ['PATH'] + ':' + '/opt/bin'
os.environ['LD_LIBRARY_PATH'] = '/opt/lib'

def lambda_handler(event, context):
    try:
        # Get the DSL code from the event
        diagram_code = event.get('diagram_code')
        if not diagram_code:
            return {
                'statusCode': 400,
                'body': json.dumps({'error': 'No diagram code provided'})
            }

        # Create a temporary directory for diagram generation
        os.makedirs('/tmp/diagram', exist_ok=True)
        os.chdir('/tmp/diagram')

        # Execute the diagram code
        local_vars = {}
        exec(diagram_code, {'Diagram': Diagram}, local_vars)

        # Find the generated PNG file
        png_files = [f for f in os.listdir('.') if f.endswith('.png')]
        if not png_files:
            raise Exception("No PNG file was generated")

        # Read the generated PNG
        with open(png_files[0], 'rb') as f:
            image_data = f.read()

        # Upload to S3
        bucket_name = os.environ['S3_BUCKET_NAME']
        s3_key = f'diagrams/{context.aws_request_id}.png'
        
        s3_client = boto3.client('s3')
        s3_client.put_object(
            Bucket=bucket_name,
            Key=s3_key,
            Body=image_data,
            ContentType='image/png'
        )

        # Generate a presigned URL (valid for 1 hour)
        presigned_url = s3_client.generate_presigned_url(
            'get_object',
            Params={
                'Bucket': bucket_name,
                'Key': s3_key
            },
            ExpiresIn=3600
        )

        # Clean up
        for file in png_files:
            os.remove(file)

        return {
            'statusCode': 200,
            'body': json.dumps({
                'url': presigned_url,
                'key': s3_key
            })
        }

    except Exception as e:
        return {
            'statusCode': 500,
            'body': json.dumps({
                'error': str(e)
            })
        }
