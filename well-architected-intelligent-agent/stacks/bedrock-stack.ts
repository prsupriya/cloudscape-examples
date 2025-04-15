import {
  Stack,
  StackProps,
  RemovalPolicy,
  CfnOutput,
  Duration,
} from 'aws-cdk-lib';
import { Construct } from 'constructs';
import * as lambda from 'aws-cdk-lib/aws-lambda';
import * as s3 from 'aws-cdk-lib/aws-s3';
import * as iam from 'aws-cdk-lib/aws-iam';
import { CfnKnowledgeBase, CfnDataSource } from 'aws-cdk-lib/aws-bedrock';
import * as opensearchserverless from 'aws-cdk-lib/aws-opensearchserverless';
import * as cr from 'aws-cdk-lib/custom-resources';


export class BedrockStack extends Stack {
  public readonly documentsBucket: s3.Bucket;

  constructor(scope: Construct, id: string, props?: StackProps) {
    super(scope, id, props);

    const region = Stack.of(this).region;
    const account = Stack.of(this).account;
    // Create a unique collection name with timestamp
    const timestamp = Math.floor(Date.now() / 1000);
    const collectionName = `bedrock-kb-collection-${timestamp}`;



    // Create encryption policy for Bedrock KB
    const encryptionPolicy: opensearchserverless.CfnSecurityPolicy = new opensearchserverless.CfnSecurityPolicy(this, 'EncryptionPolicy', {
      name: 'bedrock-kb-encryption-policy',
      type: 'encryption',
      description: 'Encryption policy for Bedrock KB collection',
      policy: JSON.stringify({
        Rules: [
          {
            ResourceType: 'collection',
            Resource: [`collection/${collectionName}`],
          },
        ],
        AWSOwnedKey: true, // Ensure this is correct if you're using AWS-managed encryption keys
      }),
    });
    
    // Create data access policy
    const dataAccessPolicy: opensearchserverless.CfnAccessPolicy = new opensearchserverless.CfnAccessPolicy(this, 'DataAccessPolicy', {
      name: 'bedrock-kb-access-policy',
      type: 'data',
      description: 'Data access policy for Bedrock KB collection',
      policy: JSON.stringify([
        {
          Rules: [
            {
              ResourceType: "collection",
              Resource: [`collection/${collectionName}`],
              Permission: [
                "aoss:CreateCollectionItems",
                "aoss:DeleteCollectionItems",
                "aoss:UpdateCollectionItems",
                "aoss:DescribeCollectionItems",
                "aoss:RestoreSnapshot",
                "aoss:DescribeSnapshot"
              ]
            }
          ],
          Principal: [
            `arn:aws:iam::${account}:role/aws-service-role/bedrock.amazonaws.com/AWSServiceRoleForAmazonBedrock`
          ]
        }
      ])
    });
    
    
    
    // Create network policy for Bedrock KB
    const networkPolicy: opensearchserverless.CfnSecurityPolicy = new opensearchserverless.CfnSecurityPolicy(this, 'NetworkPolicy', {
      name: 'bedrock-kb-network-policy',
      type: 'network',
      description: 'Network policy for Bedrock KB collection',
      policy: JSON.stringify([
        {
          Rules: [
            {
              ResourceType: 'collection',
              Resource: [`collection/${collectionName}`],
            }
          ],
          AllowFromPublic: true
        }
      ])
    });

    // Wait for encryption policy to be active
    const waitForEncryption = new cr.AwsCustomResource(this, 'WaitForEncryption', {
      onCreate: {
        service: 'OpenSearchServerless',
        action: 'getSecurityPolicy',
        parameters: {
          name: encryptionPolicy.name,
          type: 'encryption'
        },
        physicalResourceId: cr.PhysicalResourceId.of('encryption-policy-wait'),
      },
      policy: cr.AwsCustomResourcePolicy.fromSdkCalls({
        resources: cr.AwsCustomResourcePolicy.ANY_RESOURCE
      }),
    });

    waitForEncryption.node.addDependency(encryptionPolicy);
    
   

    // Create OpenSearch Serverless Collection
    const collection = new opensearchserverless.CfnCollection(this, 'BedrockKBCollection', {
      name: collectionName,
      description: 'Collection for Bedrock Knowledge Base',
      type: 'VECTORSEARCH'
    });

    // Add dependencies for collection
    collection.node.addDependency(encryptionPolicy);
    collection.node.addDependency(networkPolicy);
    collection.node.addDependency(dataAccessPolicy);

    // Wait for collection to be active
    const waitForCollection = new cr.AwsCustomResource(this, 'WaitForCollection', {
      onCreate: {
        service: 'OpenSearchServerless',
        action: 'batchGetCollection',
        parameters: {
          names: [collection.name]
        },
        physicalResourceId: cr.PhysicalResourceId.of(collection.name),
      },
      policy: cr.AwsCustomResourcePolicy.fromSdkCalls({
        resources: cr.AwsCustomResourcePolicy.ANY_RESOURCE
      }),
    });

    waitForCollection.node.addDependency(collection);

        // After collection creation but before knowledge base creation
    const getCollectionEndpoint = new cr.AwsCustomResource(this, 'GetCollectionEndpoint', {
      onCreate: {
        service: 'OpenSearchServerless',
        action: 'batchGetCollection',
        parameters: {
          names: [collectionName]
        },
        physicalResourceId: cr.PhysicalResourceId.of(`${collectionName}-endpoint`),
        outputPaths: ['collectionDetails.0.collectionEndpoint']
      },
      policy: cr.AwsCustomResourcePolicy.fromSdkCalls({
        resources: cr.AwsCustomResourcePolicy.ANY_RESOURCE
      })
    });

        // Add dependency to ensure collection exists first
    getCollectionEndpoint.node.addDependency(collection);
    getCollectionEndpoint.node.addDependency(waitForCollection);

    // Get the collection endpoint
    const collectionEndpoint = getCollectionEndpoint.getResponseField('collectionDetails.0.collectionEndpoint');

    // Add an output to verify the endpoint
    new CfnOutput(this, 'CollectionEndpoint', {
      value: collectionEndpoint,
      description: 'OpenSearch Serverless Collection Endpoint'
    });

  //  // Add this after the collection creation and before the Knowledge Base creation
  //   const createIndex = new cr.AwsCustomResource(this, 'CreateIndex', {
  //     onCreate: {
  //       service: 'OpenSearchServerless',
  //       action: 'createCollection', // First ensure we have the collection endpoint
  //       parameters: {
  //         name: collectionName,
  //       },
  //       physicalResourceId: cr.PhysicalResourceId.of(collectionName),
  //       outputPaths: ['collectionEndpoint']
  //     },
  //     policy: cr.AwsCustomResourcePolicy.fromSdkCalls({
  //       resources: cr.AwsCustomResourcePolicy.ANY_RESOURCE
  //     })
  //   });

// Now create a second custom resource to create the index using the collection endpoint
const createIndexMapping = new cr.AwsCustomResource(this, 'CreateIndexMapping', {
  onCreate: {
    service: 'Lambda',
    action: 'invoke',
    parameters: {
      FunctionName: new lambda.Function(this, 'IndexCreationFunction', {
        runtime: lambda.Runtime.NODEJS_18_X,
        handler: 'index.handler',
        code: lambda.Code.fromInline(`
          const https = require('https');
          
          exports.handler = async (event) => {
            console.log('Event:', JSON.stringify(event, null, 2));
            const indexName = 'bedrock-kb-index';
            const endpoint = event.endpoint;
            console.log('Using endpoint:', endpoint);
            
            const mapping = {
              mappings: {
                properties: {
                  AMAZON_BEDROCK_METADATA: {
                    type: 'text'
                  },
                  AMAZON_BEDROCK_TEXT_CHUNK: {
                    type: 'text'
                  },
                  'bedrock-knowledge-base-vector': {
                    type: 'knn_vector',
                    dimension: 1536,
                    method: {
                      name: 'hnsw',
                      space_type: 'l2',
                      engine: 'nmslib',
                      parameters: {
                        ef_construction: 128,
                        m: 16
                      }
                    }
                  }
                }
              }
            };
            
            const options = {
              hostname: endpoint.replace('https://', ''),
              port: 443,
              path: '/' + indexName,
              method: 'PUT',
              headers: {
                'Content-Type': 'application/json',
              }
            };
            
            return new Promise((resolve, reject) => {
              const req = https.request(options, (res) => {
                let data = '';
                res.on('data', chunk => { data += chunk; });
                res.on('end', () => {
                  console.log('Index creation response:', data);
                  resolve({ statusCode: res.statusCode, body: data });
                });
              });
              
              req.on('error', (error) => {
                console.error('Error:', error);
                reject(error);
              });
              
              req.write(JSON.stringify(mapping));
              req.end();
            });
          }
        `),
        timeout: Duration.seconds(30)
      }).functionName,
      Payload: JSON.stringify({
        endpoint: collectionEndpoint
      })
    },
    physicalResourceId: cr.PhysicalResourceId.of('create-index-mapping')
  },
  policy: cr.AwsCustomResourcePolicy.fromStatements([
    new iam.PolicyStatement({
      actions: ['lambda:InvokeFunction'],
      resources: ['*']
    })
  ])
});

// Add dependencies
createIndexMapping.node.addDependency(getCollectionEndpoint);


    // Add dependencies
    // createIndexMapping.node.addDependency(createIndex);
    // createIndexMapping.node.addDependency(collection);
    // createIndexMapping.node.addDependency(waitForCollection);

    // Create S3 bucket for documents
    this.documentsBucket = new s3.Bucket(this, 'DocumentsBucket', {
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
      description: 'Role for Bedrock to access S3 bucket and OpenSearch',
      inlinePolicies: {
        BedrockExecutionPolicy: new iam.PolicyDocument({
          statements: [
            new iam.PolicyStatement({
              effect: iam.Effect.ALLOW,
              actions: [
                'bedrock:*',
                'aoss:APIAccessAll',
                'aoss:DashboardsAccessAll'
              ],
              resources: ['*']
            })
          ]
        })
      }
    });
    

    // Add S3 permissions
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

    // Add OpenSearch Serverless permissions
    bedrockRole.addToPolicy(
      new iam.PolicyStatement({
        effect: iam.Effect.ALLOW,
        actions: [
          'aoss:APIAccessAll',
          'aoss:BatchGetCollection',
          'aoss:CreateCollection',
          'aoss:CreateSecurityPolicy',
          'aoss:GetAccessPolicy',
          'aoss:CreateAccessPolicy',
          'aoss:UpdateCollection',
          'aoss:DeleteCollection'
        ],
        resources: [`arn:aws:aoss:${region}:${account}:collection/*`]
      })
    );

    // Create Knowledge Base
    const knowledgeBase = new CfnKnowledgeBase(this, 'DocumentsKnowledgeBase', {
      name: 'documents-knowledge-base',
      description: 'Knowledge base for document processing',
      roleArn: bedrockRole.roleArn,
      knowledgeBaseConfiguration: {
        type: 'VECTOR',
        vectorKnowledgeBaseConfiguration: {
          embeddingModelArn: `arn:aws:bedrock:${region}::foundation-model/amazon.titan-embed-text-v1`
        }
      },
      storageConfiguration: {
        type: 'OPENSEARCH_SERVERLESS',
        opensearchServerlessConfiguration: {
          collectionArn: collection.attrArn,
          vectorIndexName: 'bedrock-kb-index',
          fieldMapping: {
            metadataField: 'AMAZON_BEDROCK_METADATA',
            textField: 'AMAZON_BEDROCK_TEXT_CHUNK',
            vectorField: 'bedrock-knowledge-base-vector'
          }
        }
      }
    });

    // Add dependencies using node.addDependency
    knowledgeBase.node.addDependency(collection);
    knowledgeBase.node.addDependency(networkPolicy);
    knowledgeBase.node.addDependency(encryptionPolicy);
    knowledgeBase.node.addDependency(dataAccessPolicy);
    knowledgeBase.node.addDependency(waitForCollection);
    knowledgeBase.node.addDependency(createIndexMapping);



    // Create Data Source
    const dataSource = new CfnDataSource(this, 'S3DataSource', {
      knowledgeBaseId: knowledgeBase.attrKnowledgeBaseId,
      name: 'documents-data-source',
      description: 'S3 bucket containing documents',
      dataSourceConfiguration: {
        type: 'S3',
        s3Configuration: {
          bucketArn: this.documentsBucket.bucketArn,
          inclusionPrefixes: ['documents/']
        }
      }
    });

    // Add dependency for data source
    dataSource.node.addDependency(knowledgeBase);

    // Outputs
    new CfnOutput(this, 'DocumentsBucketName', {
      value: this.documentsBucket.bucketName,
      description: 'Name of the S3 bucket containing documents'
    });

    new CfnOutput(this, 'KnowledgeBaseId', {
      value: knowledgeBase.attrKnowledgeBaseId,
      description: 'ID of the Bedrock Knowledge Base'
    });

    new CfnOutput(this, 'OpenSearchCollectionId', {
      value: collection.attrId,
      description: 'ID of the OpenSearch Serverless Collection'
    });
  }
}
