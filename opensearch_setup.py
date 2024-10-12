import json

def create_policies_in_oss(vector_store_name, aoss_client, bedrock_kb_execution_role_arn, encryption_policy_name, network_policy_name, access_policy_name):
    encryption_policy = aoss_client.create_security_policy(
        name=encryption_policy_name,
        policy=json.dumps({
            'Rules': [{'Resource': ['collection/' + vector_store_name], 'ResourceType': 'collection'}],
            'AWSOwnedKey': True
        }),
        type='encryption'
    )

    network_policy = aoss_client.create_security_policy(
        name=network_policy_name,
        policy=json.dumps([{
            'Rules': [{'Resource': ['collection/' + vector_store_name], 'ResourceType': 'collection'}],
            'AllowFromPublic': True
        }]),
        type='network'
    )

    access_policy = aoss_client.create_access_policy(
        name=access_policy_name,
        policy=json.dumps([{
            'Rules': [{'Resource': ['collection/' + vector_store_name], 'Permission': ['aoss:CreateCollectionItems'], 'ResourceType': 'collection'}],
            'Principal': [bedrock_kb_execution_role_arn]
        }]),
        type='data'
    )

    return encryption_policy, network_policy, access_policy

def create_opensearch_collection(aoss_client, vector_store_name):
    collection = aoss_client.create_collection(name=vector_store_name, type='VECTORSEARCH')
    return collection

def check_collection_status(aoss_client, vector_store_name, interactive_sleep):
    response = aoss_client.batch_get_collection(names=[vector_store_name])
    while response['collectionDetails'][0]['status'] == 'CREATING':
        print('Creating collection...')
        interactive_sleep(30)
        response = aoss_client.batch_get_collection(names=[vector_store_name])
    return response['collectionDetails']
