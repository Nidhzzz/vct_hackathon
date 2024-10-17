# main.py
import boto3
from aws_setup import create_bedrock_execution_role
from opensearch_setup import create_policies_in_oss, create_opensearch_collection, check_collection_status
from opensearchpy import OpenSearch, RequestsHttpConnection, AWSV4SignerAuth, RequestError
from s3_file_management import check_and_create_bucket, list_files_in_bucket
from knowledge_base_management import create_knowledge_base, start_ingestion_job, check_ingestion_status
from helper_functions import interactive_sleep
from cleanup import cleanup_resources
import pprint
import json
import os
import requests
from requests_aws4auth import AWS4Auth

# Set AWS credentials as environment variables
session = boto3.Session()
sts = session.client('sts')
response = sts.get_caller_identity()
# print(response)

# Set new AWS credentials and session token as environment variables
os.environ['AWS_ACCESS_KEY_ID'] = 'AKIAS2VS4CX5YKN7URUZ'
os.environ['AWS_SECRET_ACCESS_KEY'] = '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'
os.environ['AWS_DEFAULT_REGION'] = 'us-east-1'

# Setup configurations
suffix = 'vct-sakec'  # Ensure lowercase and underscores replaced with dashes
bucket_name = 'vlrscraperbucket'  # Replace with your bucket name
vector_store_name = f'bedrock-sample-rag-{suffix}'  # Ensure all lowercase
safe_suffix = suffix.replace('_', '-')
index_name = f'bedrock-sample-rag-index-{safe_suffix}'  # Ensure lowercase
description = "Amazon shareholder letter knowledge base."
region_name = boto3.session.Session().region_name
embedding_model_arn = f"arn:aws:bedrock:{region_name}::foundation-model/amazon.titan-embed-text-v1"
pp = pprint.PrettyPrinter(indent=2)

# AWS clients
boto3_session = boto3.Session(region_name='us-east-1')  # Change 'us-east-1' to your desired region
s3_client = boto3_session.client('s3')
aoss_client = boto3_session.client('opensearchserverless')
bedrock_agent_client = boto3_session.client('bedrock-agent', region_name=region_name)

# IAM Role and Policy names
fm_policy_name = f'AmazonBedrockFoundationModelPolicyForKnowledgeBase_{suffix}'
s3_policy_name = f'AmazonBedrockS3PolicyForKnowledgeBase_{suffix}'
oss_policy_name = f'AmazonBedrockOSSPolicyForKnowledgeBase_{suffix}'
bedrock_execution_role_name = f'AmazonBedrockExecutionRoleForKnowledgeBase_{suffix}'

# Creating index
def create_opensearch_index(collection_endpoint, index_name, region_name):
    try:
        session = boto3.Session()
        credentials = session.get_credentials()
        awsauth = AWSV4SignerAuth(credentials, region_name, 'aoss')

        # Define the vector index configuration (with KNN vector field and FAISS engine)
        index_config = {
            "settings": {
                "index.knn": "true",
                "number_of_shards": 1,
                "knn.algo_param.ef_search": 512,
                "number_of_replicas": 0
            },
            "mappings": {
                "properties": {
                    "vector": {
                        "type": "knn_vector",
                        "dimension": 1536,  # Example dimension size
                        "method": {
                            "name": "hnsw",
                            "engine": "faiss",  # FAISS engine
                            "space_type": "l2"
                        }
                    },
                    "text": {
                        "type": "text"
                    },
                    "text-metadata": {
                        "type": "text"
                    }
                }
            }
        }

        # Ensure the collection_endpoint does not include 'https://'
        clean_endpoint = collection_endpoint.replace('https://', '').replace('http://', '')

        # Build the OpenSearch client
        oss_client = OpenSearch(
            hosts=[{'host': clean_endpoint, 'port': 443}],
            http_auth=awsauth,
            use_ssl=True,
            verify_certs=True,
            connection_class=RequestsHttpConnection,
            timeout=300
        )

        # Check if the index already exists
        if oss_client.indices.exists(index=index_name):
            print(f"Index {index_name} already exists. Skipping creation.")
            return

        # Create the index if it doesn't exist
        print(f"Creating index {index_name} in collection {collection_endpoint}...")
        response = oss_client.indices.create(index=index_name, body=json.dumps(index_config))
        print('Index created successfully:')
        pp.pprint(response)

        # Optional: Wait for the index creation to complete (adjust time if necessary)
        interactive_sleep(60)

    except RequestError as e:
        # Handle case where index might already exist or another error occurred
        print(f"Error creating index: {e.error}")
        print("To delete the existing index and recreate, uncomment the delete command.")
        # Uncomment the following line to delete and recreate the index if needed
        # oss_client.indices.delete(index=index_name)

    except Exception as e:
        print(f"Exception during index creation: {str(e)}")

# Create the S3 bucket if it does not exist
print("Checking and creating S3 bucket if needed...")
check_and_create_bucket(s3_client, bucket_name, region_name)

# List files in the bucket
# print("Listing files in the S3 bucket:")
files = list_files_in_bucket(s3_client, bucket_name)
# pp.pprint(files)

# Create Bedrock Execution Role
bedrock_kb_execution_role_arn = create_bedrock_execution_role(bucket_name, fm_policy_name, s3_policy_name, bedrock_execution_role_name)

if bedrock_kb_execution_role_arn is None:
    print("Failed to create Bedrock execution role.")
else:
    print(f"Bedrock Execution Role ARN: {bedrock_kb_execution_role_arn}")

# Create OpenSearch security, network, and access policies
print("Creating OpenSearch policies...")
encryption_policy_name = f"bedrock-sample-rag-sp-{safe_suffix}"
network_policy_name = f"bedrock-sample-rag-np-{safe_suffix}"
access_policy_name = f'bedrock-sample-rag-ap-{safe_suffix}'
vector_store_name = f'bedrock-sample-rag-{safe_suffix}'

encryption_policy, network_policy, access_policy = create_policies_in_oss(
    vector_store_name, aoss_client, bedrock_kb_execution_role_arn,
    encryption_policy_name, network_policy_name, access_policy_name
)

# Create OpenSearch collection with detailed error logging
print("Creating OpenSearch collection...")
collection = None
try:
    collection = create_opensearch_collection(aoss_client, vector_store_name)
    if collection:
        print("OpenSearch collection created successfully.")
    else:
        print("OpenSearch collection creation failed.")
except Exception as e:
    print(f"Error creating OpenSearch collection: {e}")
if collection:
    # After checking OpenSearch collection status
    print("Checking OpenSearch collection status...")
    collection_details = check_collection_status(aoss_client, vector_store_name, interactive_sleep)
    # pp.pprint(collection_details)

    # Get the collectionEndpoint from the collection details
    collection_endpoint = collection_details[0]['collectionEndpoint']
    print(f"Collection Endpoint: {collection_endpoint}")

    # Create the OpenSearch index before creating the knowledge base
    create_opensearch_index(collection_endpoint, index_name, region_name)
    print(collection['arn'])
    print(f'Index name is: {index_name}')
    # Create the knowledge base
    print("Creating knowledge base...")
    opensearch_serverless_config = {
        "collectionArn": collection['arn'],
        "vectorIndexName": index_name,
        "fieldMapping": {
            "vectorField": "vector",
            "textField": "text",
            "metadataField": "text-metadata"
        }
    }

    chunking_strategy_config = {
        "chunkingStrategy": "FIXED_SIZE",
        "fixedSizeChunkingConfiguration": {
            "maxTokens": 512,
            "overlapPercentage": 20
        }
    }

    s3_config = {
        "bucketArn": f"arn:aws:s3:::{bucket_name}",
    }

    knowledge_base = create_knowledge_base(
        bedrock_agent_client, opensearch_serverless_config, chunking_strategy_config,
        s3_config, embedding_model_arn, f"bedrock-sample-knowledge-base-{suffix}", description, bedrock_kb_execution_role_arn
    )
    kb_id = knowledge_base['knowledgeBaseId']
    print(f"Knowledge Base created with ID: {kb_id}")

    # Start ingestion job
    print("Starting ingestion job...")
    data_source = {'dataSourceId': 'your_data_source_id'}  # Replace with actual data source ID if applicable
    job = start_ingestion_job(bedrock_agent_client, kb_id, data_source)

    # Check ingestion job status
    print("Checking ingestion job status...")
    job_status = check_ingestion_status(bedrock_agent_client, kb_id, data_source, job, interactive_sleep)
    pp.pprint(job_status)
else:
    print("Error: OpenSearch collection creation failed.")

# Cleanup resources (optional)
print("Cleaning up resources...")
if 'kb_id' in locals():  # Ensure kb_id exists before using it
    cleanup_resources(iam_client, bedrock_agent_client, aoss_client, kb_id, collection, access_policy, network_policy, encryption_policy)
else:
    print("Skipping resource cleanup since kb_id was not defined.")
