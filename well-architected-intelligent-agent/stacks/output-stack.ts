import * as cdk from 'aws-cdk-lib';
import * as lambda from 'aws-cdk-lib/aws-lambda';
import * as s3 from 'aws-cdk-lib/aws-s3';
import * as iam from 'aws-cdk-lib/aws-iam';
import { Construct } from 'constructs';

export class DiagramGeneratorStack extends cdk.Stack {
  constructor(scope: Construct, id: string, props?: cdk.StackProps) {
    super(scope, id, props);

    // Create S3 bucket for storing diagrams
    const diagramBucket = new s3.Bucket(this, 'diagrambucket', {
      removalPolicy: cdk.RemovalPolicy.DESTROY, // For development - change for production
      autoDeleteObjects: true, // For development - change for production
      encryption: s3.BucketEncryption.S3_MANAGED,
      enforceSSL: true,
      versioned: true,
      lifecycleRules: [
        {
          expiration: cdk.Duration.days(7), // Automatically delete files after 7 days
        },
      ],
    });

    // Create Lambda layer for Graphviz and other dependencies
    const diagramLayer = new lambda.LayerVersion(this, 'DiagramLayer', {
      code: lambda.Code.fromAsset('lambda-layer/opt'), 
      description: 'Layer containing Graphviz and Python dependencies',
      compatibleRuntimes: [lambda.Runtime.PYTHON_3_9],
    });

    // Create Lambda function
    const diagramGenerator = new lambda.Function(this, 'DiagramGenerator', {
      runtime: lambda.Runtime.PYTHON_3_9,
      code: lambda.Code.fromAsset('lambda/diagram-lambda'), 
      handler: 'index.lambda_handler',
      timeout: cdk.Duration.seconds(30),
      memorySize: 512,
      environment: {
        S3_BUCKET_NAME: diagramBucket.bucketName,
      },
      layers: [diagramLayer],
    });

    // Grant Lambda permissions to access S3
    diagramBucket.grantReadWrite(diagramGenerator);

    // Add additional permissions for Lambda to generate presigned URLs
    diagramGenerator.addToRolePolicy(
      new iam.PolicyStatement({
        actions: ['s3:PutObject', 's3:GetObject', 's3:DeleteObject'],
        resources: [diagramBucket.arnForObjects('*')],
      })
    );

    // Output the bucket name and function name
    new cdk.CfnOutput(this, 'BucketName', {
      value: diagramBucket.bucketName,
      description: 'Name of the S3 bucket for storing diagrams',
    });

    new cdk.CfnOutput(this, 'FunctionName', {
      value: diagramGenerator.functionName,
      description: 'Name of the Lambda function',
    });
  }
}
