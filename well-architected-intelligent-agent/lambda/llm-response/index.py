import json
import boto3
import os
from typing import Dict, Any

bedrock_runtime = boto3.client('bedrock-runtime')

def lambda_handler(event: Dict[Any, Any], context) -> Dict[Any, Any]:
    try:
        # Extract information from the input event
        input_text = event.get('inputText', '')
        session_attributes = event.get('sessionAttributes', {})
        
        # Call the LLM using Bedrock
        llm_response = invoke_model(input_text)
        
        # Construct the response
        response = {
            'messageVersion': '1.0',
            'response': {
                'actionGroup': event.get('actionGroup', ''),
                'apiPath': event.get('apiPath', ''),
                'httpMethod': event.get('httpMethod', 'POST'),
                'responseBody': {
                    'application/json': {
                        'body': llm_response
                    }
                }
            },
            'sessionAttributes': session_attributes
        }
        
        return response
        
    except Exception as e:
        return {
            'messageVersion': '1.0',
            'response': {
                'responseBody': {
                    'application/json': {
                        'body': f"Error processing request: {str(e)}"
                    }
                }
            }
        }

def invoke_model(prompt: str) -> Dict[str, Any]:
    """
    Invokes the LLM model using Amazon Bedrock
    """
    try:
        # Define the request parameters
        request_body = {
            "prompt": prompt,
            "max_tokens": 512,
            "temperature": 0.7,
            "top_p": 1,
            "stop_sequences": []
        }

        # Invoke the model
        response = bedrock_runtime.invoke_model(
            modelId='anthropic.claude-v2',  # You can change this to your preferred model
            body=json.dumps(request_body)
        )
        
        # Parse and return the response
        response_body = json.loads(response['body'].read())
        
        return {
            "status": "success",
            "generated_text": response_body.get('completion', ''),
            "model_id": "anthropic.claude-v2"
        }
        
    except Exception as e:
        return {
            "status": "error",
            "message": f"Error invoking model: {str(e)}"
        }

def process_request(input_data: str) -> Dict[str, Any]:
    """
    Process the input data and return structured response
    """
    llm_response = invoke_model(input_data)
    return {
        "status": "success",
        "llm_response": llm_response,
        "original_input": input_data
    }
