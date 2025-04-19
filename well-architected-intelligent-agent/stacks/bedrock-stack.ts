import {
  Stack,
  StackProps,
  aws_s3 as s3,
  aws_iam as iam,
  aws_lambda as lambda,
  RemovalPolicy,
  CfnOutput,
  Duration,
} from 'aws-cdk-lib';
import * as path from "node:path";
import { Construct } from 'constructs';
import * as lambda_python from '@aws-cdk/aws-lambda-python-alpha';
import { 
  bedrock
} from '@cdklabs/generative-ai-cdk-constructs';
import { FoundationModel } from 'aws-cdk-lib/aws-bedrock';

export class BedrockStack extends Stack {
  public readonly outputBucket: s3.Bucket;
  public readonly diagramGenerator: lambda_python.PythonFunction;
  public readonly pdfGenerator: lambda_python.PythonFunction;
  public readonly agent: bedrock.Agent;

  constructor(scope: Construct, id: string, props?: StackProps) {
    super(scope, id, props);

    // Create S3 bucket for storing generated diagrams and PDFs
    this.outputBucket = new s3.Bucket(this, 'diagramBucket', {
      removalPolicy: RemovalPolicy.DESTROY,
      autoDeleteObjects: true,
      blockPublicAccess: s3.BlockPublicAccess.BLOCK_ALL,
    });

    // Create Docker-based Lambda functions for each action group
    this.diagramGenerator = new lambda_python.PythonFunction(this, 'DiagramGeneratorFunction', {
      entry: 'lambda/generate_architecture_diagram',
      runtime: lambda.Runtime.PYTHON_3_9,
      index: 'app.py',
      handler: 'lambda_handler',
      timeout: Duration.minutes(5),
      memorySize: 1024,
      environment: {
        S3_BUCKET: this.outputBucket.bucketName,
        LOG_LEVEL: 'INFO',
      },
    });

    this.pdfGenerator = new lambda_python.PythonFunction(this, 'PDFGeneratorFunction', {
      entry: 'lambda/generate_pdf_documentation',
      runtime: lambda.Runtime.PYTHON_3_9,
      index: 'app.py',
      handler: 'lambda_handler',
      timeout: Duration.minutes(5),
      memorySize: 1024,
      environment: {
        OUTPUT_BUCKET: this.outputBucket.bucketName,
        LOG_LEVEL: 'INFO',
      },
    });

    // Grant Lambda functions access to the S3 bucket
    this.outputBucket.grantReadWrite(this.diagramGenerator);
    this.outputBucket.grantReadWrite(this.pdfGenerator);

    // Create the Bedrock Agent
    this.agent = new bedrock.Agent(this, 'ArchitectureIntelligenceAgent', {
      foundationModel: bedrock.BedrockFoundationModel.ANTHROPIC_CLAUDE_3_5_SONNET_V1_0,
      instruction: `You are the AWS Architecture Intelligence Agent, an expert system designed to help 
      users design and assess AWS architectures. You have two primary modes of operation:

      1. Design Mode: In this mode, you help users create new AWS architectures by gathering 
         requirements through interactive dialogue, recommending appropriate AWS services, and 
         generating architecture designs.

      2. Assessment Mode: In this mode, you analyze existing architecture documentation to provide
         validation, optimization recommendations, and identify potential issues.

      Your process for Design Mode:
      1. Engage with the customer to gather all necessary details about their business and technical requirements
      2. When you have sufficient information, use your knowledge of AWS best practices to formulate a tentative architecture
      3. Use the minigrammer library to generate an architecture diagram via the generateArchitectureDiagram action
      4. Confirm the architecture with the user, explain it at a high level, and get their approval
      5. Once the architecture is finalized, offer to create PDF documentation
      6. If requested, summarize the entire architecture in a markdown document and use the generatePDFDocumentation action

      You are extremely knowledgeable about AWS services, architecture patterns, and best practices.
      Always follow the AWS Well-Architected Framework principles in your recommendations.`,
      name: 'AWS-Architecture-Intelligence-Agent',
      userInputEnabled: true,
      codeInterpreterEnabled: false,
      shouldPrepareAgent: true,
    });

    // // Create action groups for diagram generation and PDF documentation
    // const diagramActionGroup = new bedrock.AgentActionGroup({
    //   name: 'archdiagram',
    //   description: 'Generate AWS architecture diagrams using the minigrammer library',
    //   apiSchema: bedrock.ApiSchema.fromLocalAsset(path.resolve(__dirname,'../lambda/generate_architecture_diagram/schema.json')),
    //   executor: bedrock.ActionGroupExecutor.fromlambdaFunction(this.diagramGenerator),
    // });

    // const pdfActionGroup = new bedrock.AgentActionGroup({
    //   name: 'documentation',
    //   description: 'Generate PDF documentation from markdown content and architecture diagrams',
    //   apiSchema: bedrock.ApiSchema.fromLocalAsset(path.resolve(__dirname,'../lambda/generate_pdf_documentation/schema.json')),
    //   executor: bedrock.ActionGroupExecutor.fromlambdaFunction(this.pdfGenerator),
    // });

    // Add action groups to the agent
    // this.agent.addActionGroup(diagramActionGroup);
    // this.agent.addActionGroup(pdfActionGroup);

    // Create an alias for the agent
    const agentAlias = new bedrock.AgentAlias(this, 'AgentAlias', {
      agent: this.agent,
      aliasName: 'prod',
    });

    // Output the agent alias ID for the client application
    new CfnOutput(this, 'AgentAliasId', {
      value: agentAlias.aliasId,
      description: 'The ID of the Bedrock Agent Alias',
    });

    // Output the S3 bucket name
    new CfnOutput(this, 'OutputBucketName', {
      value: this.outputBucket.bucketName,
      description: 'The name of the S3 bucket where diagrams and PDFs are stored',
    });
  }
}
