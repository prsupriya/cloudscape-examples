import {
  Stack,
  StackProps,
  RemovalPolicy,
  CfnOutput,
} from 'aws-cdk-lib';
import { Construct } from 'constructs';
import * as s3 from 'aws-cdk-lib/aws-s3';
import * as iam from 'aws-cdk-lib/aws-iam';
import { CfnKnowledgeBase, CfnDataSource } from 'aws-cdk-lib/aws-bedrock';

export class BedrockStack extends Stack {
  public readonly documentsBucket: s3.Bucket;

  constructor(scope: Construct, id: string, props?: StackProps) {
    super(scope, id, props);

    const region = Stack.of(this).region;
    const account = Stack.of(this).account;

    // Create S3 bucket for documents
    this.documentsBucket = new s3.Bucket(this, 'XXXXXXXXXXXXXXX', {
      bucketName: `bedrock-documents-${account}-${region}`,
      removalPolicy: RemovalPolicy.DESTROY,
      autoDeleteObjects: true,
      blockPublicAccess: s3.BlockPublicAccess.BLOCK_ALL,
      enforceSSL: true,
      encryption: s3.BucketEncryption.S3_MANAGED,
      versioned: true,
    });

    // Create IAM role for Bedrock
    const bedrockRole = new iam.Role(this, 'BedrockServiceRole', {
      assumedBy: new iam.ServicePrincipal('bedrock.amazonaws.com'),
      description: 'Role for Bedrock to access S3 bucket',
    });

    // Add S3 permissions to the role
    bedrockRole.addToPolicy(
      new iam.PolicyStatement({
        effect: iam.Effect.ALLOW,
        actions: [
          's3:GetObject',
          's3:ListBucket',
          's3:PutObject'
        ],
        resources: [
          this.documentsBucket.bucketArn,
          `${this.documentsBucket.bucketArn}/*`,
        ],
      })
    );

    //create knowledgebase
    const knowledgeBase = new CfnKnowledgeBase(this, 'DocumentsKnowledgeBase', {
      name: 'documents-knowledge-base',
      description: 'Knowledge base for document processing',
      roleArn: bedrockRole.roleArn,
      knowledgeBaseConfiguration: {
        type: 'VECTOR',
        embeddingModelArn: `arn:aws:bedrock:${this.region}::foundation-model/amazon.titan-embed-text-v1`
      },
      storageConfiguration: {
        type: 'OPENSEARCH_SERVERLESS',
        opensearchServerlessConfiguration: {
          collectionArn: 'arn:aws:aoss:us-east-1:123456789012:collection/documents-kb-collection', // Replace with your actual ARN
          vectorIndexName: 'documents-index',
          fieldMapping: {
            metadataField: '_metadata',
            textField: '_text',
            vectorField: '_vector'
          }
        }
      }
    });
    
    

    // Create Data Source
    const dataSource = new CfnDataSource(this, 'S3DataSource', {
      knowledgeBaseId: knowledgeBase.attrKnowledgeBaseId,
      dataSourceConfiguration: {
        name: 'documents-data-source',
        description: 'S3 bucket containing documents',
        type: 'S3',
        s3Configuration: {
          bucketArn: this.documentsBucket.bucketArn,
          inclusionPrefixes: ['documents/']  // Optional: specify prefix
        }
      }
    });

    // Outputs
    new CfnOutput(this, 'DocumentsBucketName', {
      value: this.documentsBucket.bucketName,
      description: 'Name of the S3 bucket containing documents',
      exportName: 'DocumentsBucketName'
    });

    new CfnOutput(this, 'KnowledgeBaseId', {
      value: knowledgeBase.attrKnowledgeBaseId,
      description: 'ID of the Bedrock Knowledge Base',
      exportName: 'KnowledgeBaseId'
    });

    new CfnOutput(this, 'DataSourceId', {
      value: dataSource.attrDataSourceId,
      description: 'ID of the Bedrock Data Source',
      exportName: 'DataSourceId'
    });
  }
}
