import * as cdk from 'aws-cdk-lib';
import * as lambda from 'aws-cdk-lib/aws-lambda';
import * as iam from 'aws-cdk-lib/aws-iam';
import * as path from "node:path";
import * as s3 from 'aws-cdk-lib/aws-s3';
import * as s3n from 'aws-cdk-lib/aws-s3-notifications';
import { Construct } from 'constructs';

interface LambdaStackProps extends cdk.StackProps {
  userBucket: s3.IBucket; // Add bucket as a prop
}

export class LambdaStack extends cdk.Stack {
  constructor(scope: Construct, id: string, props:cdk.StackProps) {
    super(scope, id, props);

    // ----- LLM Lambda --- // 
    // Create IAM role for Lambda
    const lambdaRole = new iam.Role(this, 'LLMLambdaRole', {
      assumedBy: new iam.ServicePrincipal('lambda.amazonaws.com'),
      description: 'Role for Lambda to interact with Bedrock',
    });

    // Add required policies to the role
    lambdaRole.addManagedPolicy(
      iam.ManagedPolicy.fromAwsManagedPolicyName('service-role/AWSLambdaBasicExecutionRole')
    );

    // Add Bedrock permissions
    lambdaRole.addToPolicy(new iam.PolicyStatement({
      effect: iam.Effect.ALLOW,
      actions: [
        'bedrock:InvokeModel',
        'bedrock:ListFoundationModels',
      ],
      resources: ['*'], // You might want to restrict this to specific model ARNs in production
    }));

    // Create Lambda function
    const llmLambda = new lambda.Function(this, 'LLMFunction', {
      runtime: lambda.Runtime.PYTHON_3_9,
      handler: 'index.lambda_handler',
      code: lambda.Code.fromAsset(path.join(__dirname, '../lambda/llm-response')), // Adjust path as needed
      role: lambdaRole,
      timeout: cdk.Duration.minutes(5),
      memorySize: 512,
      environment: {
        POWERTOOLS_SERVICE_NAME: 'llm-service',
        LOG_LEVEL: 'INFO',
      },
      tracing: lambda.Tracing.ACTIVE, // Enable X-Ray tracing
    });

    // Add the S3 notification
    // props.userBucket.addEventNotification(
    //   s3.EventType.OBJECT_CREATED_PUT,
    //   new s3n.LambdaDestination(llmLambda)
    // );

    // Grant read permissions to the Lambda
    //props.userBucket.grantRead(llmLambda);

    // Create URL for Lambda (optional)
    const functionUrl = llmLambda.addFunctionUrl({
      authType: lambda.FunctionUrlAuthType.AWS_IAM,
      cors: {
        allowedOrigins: ['*'], // Restrict in production
        allowedMethods: [lambda.HttpMethod.POST],
        allowedHeaders: ['*'],
      },
    });

    // Optional: Create CloudWatch Log Group with retention
    new cdk.aws_logs.LogGroup(this, 'LLMLambdaLogGroup', {
      logGroupName: `/aws/lambda/${llmLambda.functionName}`,
      retention: cdk.aws_logs.RetentionDays.ONE_WEEK,
      removalPolicy: cdk.RemovalPolicy.DESTROY,
    });

    // Output the function URL and ARN
    new cdk.CfnOutput(this, 'LambdaFunctionUrl', {
      value: functionUrl.url,
      description: 'URL of the Lambda function',
    });

    new cdk.CfnOutput(this, 'LambdaFunctionArn', {
      value: llmLambda.functionArn,
      description: 'ARN of the Lambda function',
    });


    // --- agent lambda -- 

    
// Create IAM role for Agent Lambda
const agentLambdaRole = new iam.Role(this, 'AgentLambdaRole', {
    assumedBy: new iam.ServicePrincipal('lambda.amazonaws.com'),
    description: 'Role for Lambda to interact with Bedrock Agent',
  });
  
  // Add required policies to the role
  agentLambdaRole.addManagedPolicy(
    iam.ManagedPolicy.fromAwsManagedPolicyName('service-role/AWSLambdaBasicExecutionRole')
  );
  
  // Add Bedrock permissions
  agentLambdaRole.addToPolicy(new iam.PolicyStatement({
    effect: iam.Effect.ALLOW,
    actions: [
      'bedrock:InvokeAgent',
      'bedrock:InvokeModel',
      'bedrock:ListAgents',
    ],
    resources: ['*'], // Consider restricting this in production
  }));
  
  // Create Agent Lambda function
  const agentLambda = new lambda.Function(this, 'AgentFunction', {
    runtime: lambda.Runtime.PYTHON_3_9,
    handler: 'index.lambda_handler',
    code: lambda.Code.fromAsset(path.join(__dirname, '../lambda/agent-response')), // Adjust path as needed
    role: agentLambdaRole,
    timeout: cdk.Duration.minutes(5),
    memorySize: 512,
    environment: {
      POWERTOOLS_SERVICE_NAME: 'agent-service',
      LOG_LEVEL: 'INFO',
    },
    tracing: lambda.Tracing.ACTIVE, // Enable X-Ray tracing
  });
  
  // Add resource-based policy to allow Bedrock to invoke the Lambda
  agentLambda.addPermission('BedrockInvokePermission', {
    principal: new iam.ServicePrincipal('bedrock.amazonaws.com'),
    action: 'lambda:InvokeFunction',
    sourceArn: `arn:aws:bedrock:${this.region}:${this.account}:agent/*`, // Adjust if needed
  });
  
  // Create URL for Agent Lambda (if needed)
  const agentFunctionUrl = agentLambda.addFunctionUrl({
    authType: lambda.FunctionUrlAuthType.AWS_IAM,
    cors: {
      allowedOrigins: ['*'], // Restrict in production
      allowedMethods: [lambda.HttpMethod.POST],
      allowedHeaders: ['*'],
    },
  });
  
  // Create CloudWatch Log Group with retention
  new cdk.aws_logs.LogGroup(this, 'AgentLambdaLogGroup', {
    logGroupName: `/aws/lambda/${agentLambda.functionName}`,
    retention: cdk.aws_logs.RetentionDays.ONE_WEEK,
    removalPolicy: cdk.RemovalPolicy.DESTROY,
  });
  
  // Output the function URL and ARN
  new cdk.CfnOutput(this, 'AgentLambdaFunctionUrl', {
    value: agentFunctionUrl.url,
    description: 'URL of the Agent Lambda function',
  });
  
  new cdk.CfnOutput(this, 'AgentLambdaFunctionArn', {
    value: agentLambda.functionArn,
    description: 'ARN of the Agent Lambda function',
  });
  

  }
}
