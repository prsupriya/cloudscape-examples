// src/services/api-service.ts

import { post } from 'aws-amplify/api';

/**
 * Service class to handle all API communications
 */
export class ChatApiService {
  /**
   * Sends chat message and files to API
   * @param message - Chat message text
   * @param files - Array of files to send
   * @returns Promise with API response
   */
  public static async sendChatMessage(message: string, files: File[]) {
    try {
      // Create FormData to send files
      const formData = new FormData();
      formData.append('message', message);
      
      // Append each file to FormData
      files.forEach(file => {
        formData.append('files', file);
      });

      // Make API call using Amplify
      const response = await post({
        apiName: 'chatApi',
        path: '/upload', // Update this path to match your API endpoint
        options: {
          body: formData
        }
      });

      return response;
    } catch (error) {
      console.error('Error sending message:', error);
      throw error;
    }
  }
}
