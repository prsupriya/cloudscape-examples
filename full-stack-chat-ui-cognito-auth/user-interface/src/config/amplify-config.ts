// src/config/amplify-config.ts

import { Amplify } from 'aws-amplify';
import { generateClient } from 'aws-amplify/api';

// Check if required environment variables are defined
if (!process.env.REACT_APP_API_ENDPOINT) {
  throw new Error('REACT_APP_API_ENDPOINT is not defined');
}

if (!process.env.REACT_APP_AWS_REGION) {
  throw new Error('REACT_APP_AWS_REGION is not defined');
}

// Configure Amplify
Amplify.configure({
  API: {
    REST: {
      chatApi: {
        endpoint: process.env.REACT_APP_API_ENDPOINT as string,
        region: process.env.REACT_APP_AWS_REGION as string
      }
    }
  }
});

// Create API client
export const api = generateClient();
