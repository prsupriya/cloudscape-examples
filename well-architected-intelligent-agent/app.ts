#!/usr/bin/env node
import "source-map-support/register";
import * as cdk from "aws-cdk-lib";
import { InfrastructureStack } from "./stacks/input-infrastructure-stack";
import { DiagramGeneratorStack } from './stacks/diagram-generator-stack';
import { LambdaStack } from './stacks/lambda-stack';
import { BedrockStack } from './stacks/bedrock-stack';


const app = new cdk.App();
const infrastructureStack = new InfrastructureStack(app, "ChatUiInfrastructureStack", {
  /* If you don't specify 'env', this stack will be environment-agnostic.
   * Account/Region-dependent features and context lookups will not work,
   * but a single synthesized template can be deployed anywhere. */
  /* Uncomment the next line to specialize this stack for the AWS Account
   * and Region that are implied by the current CLI configuration. */
  // env: { account: process.env.CDK_DEFAULT_ACCOUNT, region: process.env.CDK_DEFAULT_REGION },
  /* Uncomment the next line if you know exactly what Account and Region you
   * want to deploy the stack to. */
  // env: { account: '123456789012', region: 'us-east-1' },
  /* For more information, see https://docs.aws.amazon.com/cdk/latest/guide/environments.html */
});

new DiagramGeneratorStack(app, 'DiagramGeneratorStack');

// Create the Lambda stack and pass the bucket reference
const lambdaStack = new LambdaStack(app, 'LambdaStack', {
 // userBucket: infrastructureStack.userBucket
});

new BedrockStack(app, 'BedrockStack');


