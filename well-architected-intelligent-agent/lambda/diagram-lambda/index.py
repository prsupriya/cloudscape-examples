import json
import os
import sys
import logging
from typing import Any, Dict

# Configure logging
logger = logging.getLogger()
logger.setLevel(logging.DEBUG)

# Add the Python packages from the layer to the system path
sys.path.insert(0, '/opt/python')

# Set environment variables for Graphviz
os.environ['PATH'] = '/opt/bin:' + os.environ['PATH']
os.environ["LD_LIBRARY_PATH"] = "/opt/lib:/usr/lib64"

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
        logger.debug(f"DOT binary exists: {os.path.exists('/opt/bin/dot')}")
        
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
        
        # Execute the diagram code
        exec(diagram_code)
        
        return {
            'statusCode': 200,
            'body': json.dumps({'message': 'Diagram created successfully'})
        }
        
    except Exception as e:
        logger.error(f"Error: {str(e)}", exc_info=True)
        return {
            'statusCode': 500,
            'body': json.dumps({'error': str(e)})
        }
