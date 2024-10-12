#!/usr/bin/env python
# coding: utf-8
import warnings
warnings.filterwarnings('ignore')

get_ipython().run_line_magic('pip', 'install -U opensearch-py==2.3.1')
# %pip install -U boto3==1.33.2
get_ipython().run_line_magic('pip', 'install -U retrying==1.3.4')
get_ipython().run_line_magic('store', 'bucket_name')

# # AWS Github
import os
import json
import boto3
import random
import time
from botocore.exceptions import ClientError
import pprint
from utility import create_bedrock_execution_role, create_oss_policy_attach_bedrock_execution_role, create_policies_in_oss, interactive_sleep
from retrying import retry
from urllib.request import urlretrieve
get_ipython().run_line_magic('store', '-r')
from botocore.client import Config
from langchain_aws import ChatBedrock
from langchain.retrievers.bedrock import AmazonKnowledgeBasesRetriever

# Set AWS credentials as environment variables
os.environ['AWS_ACCESS_KEY_ID'] = 'AKIAS2VS4CX5YKN7URUZ'
os.environ['AWS_SECRET_ACCESS_KEY'] = 'SAQ79USa3dOU5qoeVAZam0aAFPcgwA6Hz7DCi5BQ'
os.environ['AWS_DEFAULT_REGION'] = 'us-east-1'  # Change to your preferred region

suffix = random.randrange(200, 900)
boto3_session = boto3.session.Session()
region_name = boto3_session.region_name
iam_client = boto3_session.client('iam')
account_number = boto3.client('sts').get_caller_identity().get('Account')
identity = boto3.client('sts').get_caller_identity()['Arn']

encryption_policy_name = f"bedrock-sample-rag-sp-{suffix}"
network_policy_name = f"bedrock-sample-rag-np-{suffix}"
access_policy_name = f'bedrock-sample-rag-ap-{suffix}'
bedrock_execution_role_name = f'AmazonBedrockExecutionRoleForKnowledgeBase_{suffix}'
fm_policy_name = f'AmazonBedrockFoundationModelPolicyForKnowledgeBase_{suffix}'
s3_policy_name = f'AmazonBedrockS3PolicyForKnowledgeBase_{suffix}'
oss_policy_name = f'AmazonBedrockOSSPolicyForKnowledgeBase_{suffix}'


def create_bedrock_execution_role(bucket_name):
    foundation_model_policy_document = {
        "Version": "2012-10-17",
        "Statement": [
            {
                "Effect": "Allow",
                "Action": [
                    "bedrock:InvokeModel",
                ],
                "Resource": [
                    f"arn:aws:bedrock:{region_name}::foundation-model/amazon.titan-embed-text-v1"
                ]
            }
        ]
    }

    s3_policy_document = {
        "Version": "2012-10-17",
        "Statement": [
            {
                "Effect": "Allow",
                "Action": [
                    "s3:GetObject",
                    "s3:ListBucket"
                ],
                "Resource": [
                    f"arn:aws:s3:::{bucket_name}",
                    f"arn:aws:s3:::{bucket_name}/*"
                ],
                "Condition": {
                    "StringEquals": {
                        "aws:ResourceAccount": f"{account_number}"
                    }
                }
            }
        ]
    }

    assume_role_policy_document = {
        "Version": "2012-10-17",
        "Statement": [
            {
                "Effect": "Allow",
                "Principal": {
                    "Service": "bedrock.amazonaws.com"
                },
                "Action": "sts:AssumeRole"
            }
        ]
    }
    # create policies based on the policy documents
    fm_policy = iam_client.create_policy(
        PolicyName=fm_policy_name,
        PolicyDocument=json.dumps(foundation_model_policy_document),
        Description='Policy for accessing foundation model',
    )

    s3_policy = iam_client.create_policy(
        PolicyName=s3_policy_name,
        PolicyDocument=json.dumps(s3_policy_document),
        Description='Policy for reading documents from s3')

    # create bedrock execution role
    bedrock_kb_execution_role = iam_client.create_role(
        RoleName=bedrock_execution_role_name,
        AssumeRolePolicyDocument=json.dumps(assume_role_policy_document),
        Description='Amazon Bedrock Knowledge Base Execution Role for accessing OSS and S3',
        MaxSessionDuration=3600
    )

    # fetch arn of the policies and role created above
    bedrock_kb_execution_role_arn = bedrock_kb_execution_role['Role']['Arn']
    s3_policy_arn = s3_policy["Policy"]["Arn"]
    fm_policy_arn = fm_policy["Policy"]["Arn"]

    # attach policies to Amazon Bedrock execution role
    iam_client.attach_role_policy(
        RoleName=bedrock_kb_execution_role["Role"]["RoleName"],
        PolicyArn=fm_policy_arn
    )
    iam_client.attach_role_policy(
        RoleName=bedrock_kb_execution_role["Role"]["RoleName"],
        PolicyArn=s3_policy_arn
    )
    return bedrock_kb_execution_role


def create_oss_policy_attach_bedrock_execution_role(collection_id, bedrock_kb_execution_role):
    # define oss policy document
    oss_policy_document = {
        "Version": "2012-10-17",
        "Statement": [
            {
                "Effect": "Allow",
                "Action": [
                    "aoss:APIAccessAll"
                ],
                "Resource": [
                    f"arn:aws:aoss:{region_name}:{account_number}:collection/{collection_id}"
                ]
            }
        ]
    }
    oss_policy = iam_client.create_policy(
        PolicyName=oss_policy_name,
        PolicyDocument=json.dumps(oss_policy_document),
        Description='Policy for accessing opensearch serverless',
    )
    oss_policy_arn = oss_policy["Policy"]["Arn"]
    print("Opensearch serverless arn: ", oss_policy_arn)

    iam_client.attach_role_policy(
        RoleName=bedrock_kb_execution_role["Role"]["RoleName"],
        PolicyArn=oss_policy_arn
    )
    return None


def create_policies_in_oss(vector_store_name, aoss_client, bedrock_kb_execution_role_arn):
    encryption_policy = aoss_client.create_security_policy(
        name=encryption_policy_name,
        policy=json.dumps(
            {
                'Rules': [{'Resource': ['collection/' + vector_store_name],
                           'ResourceType': 'collection'}],
                'AWSOwnedKey': True
            }),
        type='encryption'
    )

    network_policy = aoss_client.create_security_policy(
        name=network_policy_name,
        policy=json.dumps(
            [
                {'Rules': [{'Resource': ['collection/' + vector_store_name],
                            'ResourceType': 'collection'}],
                 'AllowFromPublic': True}
            ]),
        type='network'
    )
    access_policy = aoss_client.create_access_policy(
        name=access_policy_name,
        policy=json.dumps(
            [
                {
                    'Rules': [
                        {
                            'Resource': ['collection/' + vector_store_name],
                            'Permission': [
                                'aoss:CreateCollectionItems',
                                'aoss:DeleteCollectionItems',
                                'aoss:UpdateCollectionItems',
                                'aoss:DescribeCollectionItems'],
                            'ResourceType': 'collection'
                        },
                        {
                            'Resource': ['index/' + vector_store_name + '/*'],
                            'Permission': [
                                'aoss:CreateIndex',
                                'aoss:DeleteIndex',
                                'aoss:UpdateIndex',
                                'aoss:DescribeIndex',
                                'aoss:ReadDocument',
                                'aoss:WriteDocument'],
                            'ResourceType': 'index'
                        }],
                    'Principal': [identity, bedrock_kb_execution_role_arn],
                    'Description': 'Easy data policy'}
            ]),
        type='data'
    )
    return encryption_policy, network_policy, access_policy

def delete_iam_role_and_policies():
    fm_policy_arn = f"arn:aws:iam::{account_number}:policy/{fm_policy_name}"
    s3_policy_arn = f"arn:aws:iam::{account_number}:policy/{s3_policy_name}"
    oss_policy_arn = f"arn:aws:iam::{account_number}:policy/{oss_policy_name}"
    iam_client.detach_role_policy(
        RoleName=bedrock_execution_role_name,
        PolicyArn=s3_policy_arn
    )
    iam_client.detach_role_policy(
        RoleName=bedrock_execution_role_name,
        PolicyArn=fm_policy_arn
    )
    iam_client.detach_role_policy(
        RoleName=bedrock_execution_role_name,
        PolicyArn=oss_policy_arn
    )
    iam_client.delete_role(RoleName=bedrock_execution_role_name)
    iam_client.delete_policy(PolicyArn=s3_policy_arn)
    iam_client.delete_policy(PolicyArn=fm_policy_arn)
    iam_client.delete_policy(PolicyArn=oss_policy_arn)
    return 0

def interactive_sleep(seconds: int):
    dots = ''
    for i in range(seconds):
        dots += '.'
        print(dots, end='\r')
        time.sleep(1)
    # print('Done!')

suffix = 'VCT_SAKEC'

sts_client = boto3.client('sts')
boto3_session = boto3.session.Session()
region_name = boto3_session.region_name
bedrock_agent_client = boto3_session.client('bedrock-agent', region_name=region_name)
service = 'aoss'
s3_client = boto3.client('s3')
account_id = sts_client.get_caller_identity()["Account"]
s3_suffix = f"{region_name}-{account_id}"
bucket_name = f'vlrscraperbucket' # replace it with your bucket name.
pp = pprint.PrettyPrinter(indent=2)

# # Check if bucket exists, and if not create S3 bucket for knowledge base data source
# try:
#     s3_client.head_bucket(Bucket=bucket_name)
#     print(f'Bucket {bucket_name} Exists')
# except ClientError as e:
#     print(f'Creating bucket {bucket_name}')
#     if region_name == "us-east-1":
#         s3bucket = s3_client.create_bucket(
#             Bucket=bucket_name)
#     else:
#         s3bucket = s3_client.create_bucket(
#         Bucket=bucket_name,
#         CreateBucketConfiguration={ 'LocationConstraint': region_name }
#     )



# Create a session and S3 client
boto3_session = boto3.session.Session()
s3_client = boto3_session.client('s3')

# Define the bucket name
suffix = random.randrange(200, 900)
region_name = boto3_session.region_name
account_id = boto3.client('sts').get_caller_identity()["Account"]
s3_suffix = f"us-east-1-{account_id}"  # Corrected: 'us-east-1' should be in quotes
bucket_name = f'vlrscraperbucket'  # Replace this with your bucket name.

# Check if bucket exists, and if not create S3 bucket for knowledge base data source
try:
    s3_client.head_bucket(Bucket=bucket_name)
    print(f'Bucket {bucket_name} Exists')
except ClientError:
    print(f'Creating bucket {bucket_name}')
    if region_name == "us-east-1":
        s3_client.create_bucket(Bucket=bucket_name)
    else:
        s3_client.create_bucket(
            Bucket=bucket_name,
            CreateBucketConfiguration={'LocationConstraint': region_name}
        )

# List files in the S3 bucket and store information
file_info = []  # Initialize a list to store file information
try:
    response = s3_client.list_objects_v2(Bucket=bucket_name)
    if 'Contents' in response:
        print("Files in the bucket:")
        for obj in response['Contents']:
            print(obj['Key'])  # Print the file path/key in the bucket
            file_info.append(obj['Key'])  # Store file key in the list
    else:
        print(f"No files found in bucket {bucket_name}.")
except ClientError as e:
    print(f"Error listing files: {str(e)}")

# Store the file information in the variable
bucket_file_info = file_info  # You can use this variable as needed



vector_store_name = f'bedrock-sample-rag-{suffix}'
index_name = f"bedrock-sample-rag-index-{suffix}"
aoss_client = boto3_session.client('opensearchserverless')
bedrock_kb_execution_role = create_bedrock_execution_role(bucket_name=bucket_name)
bedrock_kb_execution_role_arn = bedrock_kb_execution_role['Role']['Arn']

# create security, network and data access policies within OSS
encryption_policy, network_policy, access_policy = create_policies_in_oss(vector_store_name=vector_store_name,
                       aoss_client=aoss_client,
                       bedrock_kb_execution_role_arn=bedrock_kb_execution_role_arn)
collection = aoss_client.create_collection(name=vector_store_name,type='VECTORSEARCH')

pp.pprint(collection)

get_ipython().run_line_magic('store', 'encryption_policy network_policy access_policy collection')

# Get the OpenSearch serverless collection URL
collection_id = collection['createCollectionDetail']['id']
host = collection_id + '.' + region_name + '.aoss.amazonaws.com'
print(host)

# wait for collection creation
# This can take couple of minutes to finish
response = aoss_client.batch_get_collection(names=[vector_store_name])
# Periodically check collection status
while (response['collectionDetails'][0]['status']) == 'CREATING':
    print('Creating collection...')
    interactive_sleep(30)
    response = aoss_client.batch_get_collection(names=[vector_store_name])
print('\nCollection successfully created:')
pp.pprint(response["collectionDetails"])

# create opensearch serverless access policy and attach it to Bedrock execution role
try:
    create_oss_policy_attach_bedrock_execution_role(collection_id=collection_id,
                                                    bedrock_kb_execution_role=bedrock_kb_execution_role)
    # It can take up to a minute for data access rules to be enforced
    interactive_sleep(60)
except Exception as e:
    print("Policy already exists")
    pp.pprint(e)


# # Step 2 - Create vector index
# Create the vector index in Opensearch serverless, with the knn_vector field index mapping, specifying the dimension size, name and engine.
from opensearchpy import OpenSearch, RequestsHttpConnection, AWSV4SignerAuth, RequestError
credentials = boto3.Session().get_credentials()
awsauth = auth = AWSV4SignerAuth(credentials, region_name, service)

index_name = f"bedrock-sample-index-{suffix}"
body_json = {
   "settings": {
      "index.knn": "true",
       "number_of_shards": 1,
       "knn.algo_param.ef_search": 512,
       "number_of_replicas": 0,
   },
   "mappings": {
      "properties": {
         "vector": {
            "type": "knn_vector",
            "dimension": 1536,
             "method": {
                 "name": "hnsw",
                 "engine": "faiss",
                 "space_type": "l2"
             },
         },
         "text": {
            "type": "text"
         },
         "text-metadata": {
            "type": "text"         }
      }
   }
}

# Build the OpenSearch client
oss_client = OpenSearch(
    hosts=[{'host': host, 'port': 443}],
    http_auth=awsauth,
    use_ssl=True,
    verify_certs=True,
    connection_class=RequestsHttpConnection,
    timeout=300
)

# Create index
try:
    response = oss_client.indices.create(index=index_name, body=json.dumps(body_json))
    print('\nCreating index:')
    pp.pprint(response)

    # index creation can take up to a minute
    interactive_sleep(60)
except RequestError as e:
    # you can delete the index if its already exists
    # oss_client.indices.delete(index=index_name)
    print(f'Error while trying to create the index, with error {e.error}\nyou may unmark the delete above to delete, and recreate the index')



# Create the directory if it doesn't exist
data_root = "./data/"
os.makedirs(data_root, exist_ok=True)

# List of URLs and filenames
urls = [
    'https://s2.q4cdn.com/299287126/files/doc_financials/2023/ar/2022-Shareholder-Letter.pdf',
    'https://s2.q4cdn.com/299287126/files/doc_financials/2022/ar/2021-Shareholder-Letter.pdf',
    'https://s2.q4cdn.com/299287126/files/doc_financials/2021/ar/Amazon-2020-Shareholder-Letter-and-1997-Shareholder-Letter.pdf',
    'https://s2.q4cdn.com/299287126/files/doc_financials/2020/ar/2019-Shareholder-Letter.pdf'
]

filenames = [
    'AMZN-2022-Shareholder-Letter.pdf',
    'AMZN-2021-Shareholder-Letter.pdf',
    'AMZN-2020-Shareholder-Letter.pdf',
    'AMZN-2019-Shareholder-Letter.pdf'
]

# Download the files
for idx, url in enumerate(urls):
    file_path = data_root + filenames[idx]
    urlretrieve(url, file_path)
    print(f"Downloaded {filenames[idx]} to {file_path}")


# # Upload data to S3 Bucket data source
# 

# Upload data to s3 to the bucket that was configured as a data source to the knowledge base
s3_client = boto3.client("s3")
def uploadDirectory(path,bucket_name):
        for root,dirs,files in os.walk(path):
            for file in files:
                s3_client.upload_file(os.path.join(root,file),bucket_name,file)

uploadDirectory(data_root, bucket_name)


# # Create Knowledge Base
# 
# Steps:
# 
# initialize Open search serverless configuration which will include collection ARN, index name, vector field, text field and metadata field.
# 
# initialize chunking strategy, based on which KB will split the documents into pieces of size equal to the chunk size mentioned in the chunkingStrategyConfiguration.
# 
# initialize the s3 configuration, which will be used to create the data source object later.
# 
# initialize the Titan embeddings model ARN, as this will be used to create the embeddings for each of the text chunks.
opensearchServerlessConfiguration = {
            "collectionArn": collection["createCollectionDetail"]['arn'],
            "vectorIndexName": index_name,
            "fieldMapping": {
                "vectorField": "vector",
                "textField": "text",
                "metadataField": "text-metadata"
            }
        }

# Ingest strategy - How to ingest data from the data source
chunkingStrategyConfiguration = {
    "chunkingStrategy": "FIXED_SIZE",
    "fixedSizeChunkingConfiguration": {
        "maxTokens": 512,
        "overlapPercentage": 20
    }
}

# The data source to ingest documents from, into the OpenSearch serverless knowledge base index
s3Configuration = {
    "bucketArn": f"arn:aws:s3:::{bucket_name}",
    # "inclusionPrefixes":["*.*"] # you can use this if you want to create a KB using data within s3 prefixes.
}

# The embedding model used by Bedrock to embed ingested documents, and realtime prompts
embeddingModelArn = f"arn:aws:bedrock:{region_name}::foundation-model/amazon.titan-embed-text-v1"

name = f"bedrock-sample-knowledge-base-{suffix}"
description = "Amazon shareholder letter knowledge base."
roleArn = bedrock_kb_execution_role_arn

# Provide the above configurations as input to the create_knowledge_base method, which will create the Knowledge base.
# Create a KnowledgeBase


@retry(wait_random_min=1000, wait_random_max=2000,stop_max_attempt_number=7)
def create_knowledge_base_func():
    create_kb_response = bedrock_agent_client.create_knowledge_base(
        name = name,
        description = description,
        roleArn = roleArn,
        knowledgeBaseConfiguration = {
            "type": "VECTOR",
            "vectorKnowledgeBaseConfiguration": {
                "embeddingModelArn": embeddingModelArn
            }
        },
        storageConfiguration = {
            "type": "OPENSEARCH_SERVERLESS",
            "opensearchServerlessConfiguration":opensearchServerlessConfiguration
        }
    )
    return create_kb_response["knowledgeBase"]

try:
    kb = create_knowledge_base_func()
except Exception as err:
    print(f"{err=}, {type(err)=}")

pp.pprint(kb)

# Get KnowledgeBase 
get_kb_response = bedrock_agent_client.get_knowledge_base(knowledgeBaseId = kb['knowledgeBaseId'])

# Next we need to create a data source, which will be associated with the knowledge base created above. Once the data source is ready, we can then start to ingest the documents.

# Create a DataSource in KnowledgeBase 
create_ds_response = bedrock_agent_client.create_data_source(
    name = name,
    description = description,
    knowledgeBaseId = kb['knowledgeBaseId'],
    dataSourceConfiguration = {
        "type": "S3",
        "s3Configuration":s3Configuration
    },
    vectorIngestionConfiguration = {
        "chunkingConfiguration": chunkingStrategyConfiguration
    }
)
ds = create_ds_response["dataSource"]
pp.pprint(ds)

# Start an ingestion job
interactive_sleep(30)
start_job_response = bedrock_agent_client.start_ingestion_job(knowledgeBaseId = kb['knowledgeBaseId'], dataSourceId = ds["dataSourceId"])

job = start_job_response["ingestionJob"]
pp.pprint(job)


# Get job 
while(job['status']!='COMPLETE' ):
    get_job_response = bedrock_agent_client.get_ingestion_job(
      knowledgeBaseId = kb['knowledgeBaseId'],
        dataSourceId = ds["dataSourceId"],
        ingestionJobId = job["ingestionJobId"]
  )
    job = get_job_response["ingestionJob"]
    
    interactive_sleep(30)

pp.pprint(job)

# Print the knowledge base Id in bedrock, that corresponds to the Opensearch index in the collection we created before, we will use it for the invocation later
kb_id = kb["knowledgeBaseId"]
pp.pprint(kb_id)

# keep the kb_id for invocation later in the invoke request
get_ipython().run_line_magic('store', 'kb_id')


# # Test the knowledge base
# 
# ## Note: If you plan to run any following notebooks, you can skip this section
# 
# ## Using RetrieveAndGenerate API
# 
# Behind the scenes, RetrieveAndGenerate API converts queries into embeddings, searches the knowledge base, and then augments the foundation model prompt with the search results as context information and returns the FM-generated response to the question. For multi-turn conversations, Knowledge Bases manage short-term memory of the conversation to provide more contextual results.
# 
# The output of the RetrieveAndGenerate API includes the generated response, source attribution as well as the retrieved text chunks.

# try out KB using RetrieveAndGenerate API
bedrock_agent_runtime_client = boto3.client("bedrock-agent-runtime", region_name=region_name)
# Lets see how different Anthropic Claude 3 models responds to the input text we provide
claude_model_ids = [ ["Claude 3 Sonnet", "anthropic.claude-3-sonnet-20240229-v1:0"]]

def ask_bedrock_llm_with_knowledge_base(query: str, model_arn: str, kb_id: str) -> str:
    response = bedrock_agent_runtime_client.retrieve_and_generate(
        input={
            'text': query
        },
        retrieveAndGenerateConfiguration={
            'type': 'KNOWLEDGE_BASE',
            'knowledgeBaseConfiguration': {
                'knowledgeBaseId': kb_id,
                'modelArn': model_arn
            }
        },
    )

    return response

query = "give a team with agents that dont overlap"

for model_id in claude_model_ids:
    model_arn = f'arn:aws:bedrock:{region_name}::foundation-model/{model_id[1]}'
    response = ask_bedrock_llm_with_knowledge_base(query, model_arn, kb_id)
    generated_text = response['output']['text']
    citations = response["citations"]
    contexts = []
    for citation in citations:
        retrievedReferences = citation["retrievedReferences"]
        for reference in retrievedReferences:
            contexts.append(reference["content"]["text"])
    print(f"---------- Generated using {model_id[0]}:")
    pp.pprint(generated_text )
    #print(f'---------- The citations for the response generated by {model_id[0]}:')

# # Retrieve API
# 
# Retrieve API converts user queries into embeddings, searches the knowledge base, and returns the relevant results, giving you more control to build custom workﬂows on top of the semantic search results. The output of the Retrieve API includes the the retrieved text chunks, the location type and URI of the source data, as well as the relevance scores of the retrievals.

# retrieve api for fetching only the relevant context.
relevant_documents = bedrock_agent_runtime_client.retrieve(
    retrievalQuery= {
        'text': query
    },
    knowledgeBaseId=kb_id,
    retrievalConfiguration= {
        'vectorSearchConfiguration': {
            'numberOfResults': 3 # will fetch top 3 documents which matches closely with the query.
        }
    }
)

pp.pprint(relevant_documents["retrievalResults"])

# # Building Q&A application using Knowledge Bases for Amazon Bedrock - RetrieveAndGenerate API
pp = pprint.PrettyPrinter(indent=2)

bedrock_config = Config(connect_timeout=120, read_timeout=120, retries={'max_attempts': 0})
bedrock_client = boto3.client('bedrock-runtime')
bedrock_agent_client = boto3.client("bedrock-agent-runtime",
                              config=bedrock_config)
boto3_session = boto3.session.Session()
region_name = boto3_session.region_name

model_id = "anthropic.claude-3-haiku-20240307-v1:0" # try with both claude 3 Haiku as well as claude 3 Sonnet. for claude 3 Sonnet - "anthropic.claude-3-sonnet-20240229-v1:0"
region_id = region_name # replace it with the region you're running sagemaker notebook

# # RetreiveAndGenerate API
# 
# Behind the scenes, RetrieveAndGenerate API converts queries into embeddings, searches the knowledge base, and then augments the foundation model prompt with the search results as context information and returns the FM-generated response to the question. For multi-turn conversations, Knowledge Bases manage short-term memory of the conversation to provide more contextual results.
# 
# The output of the RetrieveAndGenerate API includes the generated response, source attribution as well as the retrieved text chunks.

def retrieveAndGenerate(input, kbId, sessionId=None, model_id = "anthropic.claude-3-haiku-20240307-v1:0", region_id = "us-east-1"):
    model_arn = f'arn:aws:bedrock:{region_id}::foundation-model/{model_id}'
    if sessionId:
        return bedrock_agent_client.retrieve_and_generate(
            input={
                'text': input
            },
            retrieveAndGenerateConfiguration={
                'type': 'KNOWLEDGE_BASE',
                'knowledgeBaseConfiguration': {
                    'knowledgeBaseId': kbId,
                    'modelArn': model_arn
                }
            },
            sessionId=sessionId
        )
    else:
        return bedrock_agent_client.retrieve_and_generate(
            input={
                'text': input
            },
            retrieveAndGenerateConfiguration={
                'type': 'KNOWLEDGE_BASE',
                'knowledgeBaseConfiguration': {
                    'knowledgeBaseId': kbId,
                    'modelArn': model_arn
                }
            }
        )

query = "What is Amazon's doing in the field of generative AI?"
response = retrieveAndGenerate(query, kb_id,model_id=model_id,region_id=region_id)
generated_text = response['output']['text']
pp.pprint(generated_text)

citations = response["citations"]
contexts = []
for citation in citations:
    retrievedReferences = citation["retrievedReferences"]
    for reference in retrievedReferences:
         contexts.append(reference["content"]["text"])

pp.pprint(contexts)

get_ipython().run_line_magic('pip', "install -q -U langchain-aws=='0.1.17'")

get_ipython().system('pip show boto3 botocore')

get_ipython().run_line_magic('store', '-r')


# restart kernel
from IPython.core.display import HTML
HTML("<script>Jupyter.notebook.kernel.restart()</script>")

pp = pprint.PrettyPrinter(indent=2)
session = boto3.session.Session()
region = session.region_name
bedrock_config = Config(connect_timeout=120, read_timeout=120, retries={'max_attempts': 0})
bedrock_client = boto3.client('bedrock-runtime', region_name = region)
bedrock_agent_client = boto3.client("bedrock-agent-runtime",
                              config=bedrock_config, region_name = region)
print(region)


def retrieve(query, kbId, numberOfResults=5):
    return bedrock_agent_client.retrieve(
        retrievalQuery= {
            'text': query
        },
        knowledgeBaseId=kbId,
        retrievalConfiguration= {
            'vectorSearchConfiguration': {
                'numberOfResults': numberOfResults,
                'overrideSearchType': "HYBRID", # optional
            }
        }
    )

query = "What is Amazon doing in the field of generative AI?"
response = retrieve(query, kb_id, 5)
retrievalResults = response['retrievalResults']
pp.pprint(retrievalResults)

# fetch context from the response
def get_contexts(retrievalResults):
    contexts = []
    for retrievedResult in retrievalResults: 
        contexts.append(retrievedResult['content']['text'])
    return contexts

contexts = get_contexts(retrievalResults)
pp.pprint(contexts)


# # Prompt specific to the model to personalize responses
# 
# Here, we will use the specific prompt below for the model to act as a financial advisor AI system that will provide answers to questions by using fact based and statistical information when possible. We will provide the Retrieve API responses from above as a part of the {contexts} in the prompt for the model to refer to, along with the user query.

prompt = f"""
Human: You are a financial advisor AI system, and provides answers to questions by using fact based and statistical information when possible. 
Use the following pieces of information to provide a concise answer to the question enclosed in <question> tags. 
If you don't know the answer, just say that you don't know, don't try to make up an answer.
<context>
{contexts}
</context>

<question>
{query}
</question>

The response should be specific and use statistics or numbers when possible.

Assistant:"""


# # LangChain integration



llm = ChatBedrock(model_id="anthropic.claude-3-haiku-20240307-v1:0",
              client = bedrock_client)

# # Sab Delete  

get_ipython().run_line_magic('store', '-r')


boto3_session = boto3.Session()
bedrock_agent_client = boto3_session.client('bedrock-agent', region_name=boto3_session.region_name)
aoss_client = boto3.client('opensearchserverless')
s3_client = boto3_session.client('s3', region_name=boto3_session.region_name)
iam_client = boto3.client("iam")


response = bedrock_agent_client.list_data_sources(
    knowledgeBaseId=kb_id,
)
data_source_ids = [ x['dataSourceId'] for x in response['dataSourceSummaries']]

for data_source_id in data_source_ids:
    bedrock_agent_client.delete_data_source(dataSourceId = data_source_id, knowledgeBaseId=kb_id)


response = bedrock_agent_client.list_data_sources(
    knowledgeBaseId=kb_id,
)
data_source_ids = [ x['dataSourceId'] for x in response['dataSourceSummaries']]

for data_source_id in data_source_ids:
    bedrock_agent_client.delete_data_source(dataSourceId = data_source_id, knowledgeBaseId=kb_id)

response = bedrock_agent_client.get_knowledge_base(knowledgeBaseId=kb_id)

kb_role_name = response['knowledgeBase']['roleArn'].split("/")[-1]

kb_attached_role_policies_response = iam_client.list_attached_role_policies(
    RoleName=kb_role_name)


kb_attached_role_policies = kb_attached_role_policies_response['AttachedPolicies']

bedrock_agent_client.delete_knowledge_base(knowledgeBaseId=kb_id)
aoss_client.delete_collection(id=collection['createCollectionDetail']['id'])
aoss_client.delete_access_policy(type="data", name=access_policy['accessPolicyDetail']['name'])
aoss_client.delete_security_policy(type="network", name=network_policy['securityPolicyDetail']['name'])
aoss_client.delete_security_policy(type="encryption", name=encryption_policy['securityPolicyDetail']['name'])


for policy in kb_attached_role_policies:
    iam_client.detach_role_policy(
            RoleName=kb_role_name,
            PolicyArn=policy['PolicyArn']
    )

iam_client.delete_role(RoleName=kb_role_name)

for policy in kb_attached_role_policies:
    iam_client.delete_policy(PolicyArn=policy['PolicyArn'])


objects = s3_client.list_objects(Bucket=bucket_name)
if 'Contents' in objects:
    for obj in objects['Contents']:
        s3_client.delete_object(Bucket=bucket_name, Key=obj['Key'])
s3_client.delete_bucket(Bucket=bucket_name)
