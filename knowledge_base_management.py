import boto3

def create_knowledge_base(bedrock_agent_client, opensearchServerlessConfiguration, chunkingStrategyConfiguration, s3Configuration, embeddingModelArn, name, description, roleArn):
    create_kb_response = bedrock_agent_client.create_knowledge_base(
        name=name,
        description=description,
        roleArn=roleArn,
        knowledgeBaseConfiguration={
            "type": "VECTOR",
            "vectorKnowledgeBaseConfiguration": {
                "embeddingModelArn": embeddingModelArn
            }
        },
        storageConfiguration={
            "type": "OPENSEARCH_SERVERLESS",
            "opensearchServerlessConfiguration": opensearchServerlessConfiguration
        }
    )
    return create_kb_response['knowledgeBase']

def start_ingestion_job(bedrock_agent_client, kb_id, ds):
    start_job_response = bedrock_agent_client.start_ingestion_job(knowledgeBaseId=kb_id, dataSourceId=ds["dataSourceId"])
    return start_job_response["ingestionJob"]

def check_ingestion_status(bedrock_agent_client, kb_id, ds, job, interactive_sleep):
    while job['status'] != 'COMPLETE':
        get_job_response = bedrock_agent_client.get_ingestion_job(
            knowledgeBaseId=kb_id, dataSourceId=ds["dataSourceId"], ingestionJobId=job["ingestionJobId"]
        )
        job = get_job_response['ingestionJob']
       
