import boto3
from aws_setup import create_bedrock_execution_role
from opensearch_setup import create_policies_in_oss, create_opensearch_collection, check_collection_status
from s3_file_management import check_and_create_bucket, list_files_in_bucket
from knowledge_base_management import create_knowledge_base, start_ingestion_job, check_ingestion_status
from helper_functions import interactive_sleep
from cleanup import cleanup_resources
import pprint
import os


# Set AWS credentials as environment variables
os.environ['AWS_ACCESS_KEY_ID'] = 'AKIAS2VS4CX5YKN7URUZ'
os.environ['AWS_SECRET_ACCESS_KEY'] = 'SAQ79USa3dOU5qoeVAZam0aAFPcgwA6Hz7DCi5BQ'
os.environ['AWS_DEFAULT_REGION'] = 'us-east-1'  # Change to your preferred region

# Setup configurations
suffix = 'VCT_SAKEC'
bucket_name = 'vlrscraperbucket'  # Replace with your bucket name
vector_store_name = f'bedrock-sample-rag-{suffix}'
index_name = f'bedrock-sample-rag-index-{suffix}'
description = "Amazon shareholder letter knowledge base."
region_name = boto3.session.Session().region_name
embedding_model_arn = f"arn:aws:bedrock:{region_name}::foundation-model/amazon.titan-embed-text-v1"
pp = pprint.PrettyPrinter(indent=2)

# AWS clients
boto3_session = boto3.session.Session()
s3_client = boto3.client('s3')
# Ensure you provide the region explicitly while creating the session
boto3_session = boto3.Session(region_name='us-east-1')  # Change 'us-east-1' to your desired region
aoss_client = boto3_session.client('opensearchserverless')
bedrock_agent_client = boto3_session.client('bedrock-agent', region_name=region_name)

# IAM Role and Policy names
fm_policy_name = f'AmazonBedrockFoundationModelPolicyForKnowledgeBase_{suffix}'
s3_policy_name = f'AmazonBedrockS3PolicyForKnowledgeBase_{suffix}'
oss_policy_name = f'AmazonBedrockOSSPolicyForKnowledgeBase_{suffix}'
bedrock_execution_role_name = f'AmazonBedrockExecutionRoleForKnowledgeBase_{suffix}'

# Create the S3 bucket if it does not exist
print("Checking and creating S3 bucket if needed...")
check_and_create_bucket(s3_client, bucket_name, region_name)

# List files in the bucket
print("Listing files in the S3 bucket:")
files = list_files_in_bucket(s3_client, bucket_name)
pp.pprint(files)

# Create Bedrock Execution Role
bedrock_kb_execution_role_arn = create_bedrock_execution_role(bucket_name, fm_policy_name, s3_policy_name, bedrock_execution_role_name)

if bedrock_kb_execution_role_arn is None:
    print("Failed to create Bedrock execution role.")
else:
    print(f"Bedrock Execution Role ARN: {bedrock_kb_execution_role_arn}")


# Create OpenSearch security, network, and access policies
print("Creating OpenSearch policies...")
# Update the suffix to comply with naming rules
safe_suffix = suffix.lower().replace('_', '-')  # Convert to lowercase and replace underscores with hyphens

# Use the safe_suffix in policy names
encryption_policy_name = f"bedrock-sample-rag-sp-{safe_suffix}"
network_policy_name = f"bedrock-sample-rag-np-{safe_suffix}"
access_policy_name = f'bedrock-sample-rag-ap-{safe_suffix}'


# Update the suffix and vector store name to comply with OpenSearch naming rules
safe_suffix = suffix.lower().replace('_', '-')  # Convert to lowercase and replace underscores with hyphens
vector_store_name = f'bedrock-sample-rag-{safe_suffix}'  # Ensure this is lowercase and safe

# Use the safe vector store name for OpenSearch
encryption_policy, network_policy, access_policy = create_policies_in_oss(
    vector_store_name, aoss_client, bedrock_kb_execution_role_arn,
    encryption_policy_name, network_policy_name, access_policy_name
)


# Create OpenSearch collection
print("Creating OpenSearch collection...")
collection = create_opensearch_collection(aoss_client, vector_store_name)
pp.pprint(collection)

# Check OpenSearch collection status
print("Checking OpenSearch collection status...")
collection_details = check_collection_status(aoss_client, vector_store_name, interactive_sleep)
pp.pprint(collection_details)

# Create the knowledge base
print("Creating knowledge base...")
opensearch_serverless_config = {
    "collectionArn": collection["createCollectionDetail"]['arn'],
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

# Cleanup resources (optional)
# Uncomment if you want to clean up after the process
iam_client = boto3_session.client('iam')
print("Cleaning up resources...")
cleanup_resources(iam_client, bedrock_agent_client, aoss_client, kb_id, collection, access_policy, network_policy, encryption_policy)

