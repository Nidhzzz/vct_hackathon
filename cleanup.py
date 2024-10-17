import boto3

def cleanup_resources(iam_client, bedrock_agent_client, aoss_client, kb_id, collection, access_policy, network_policy, encryption_policy):
    # Cleanup IAM roles, policies, OpenSearch collections
    response = bedrock_agent_client.get_knowledge_base(knowledgeBaseId=kb_id)
    kb_role_name = response['knowledgeBase']['roleArn'].split('/')[-1]
    kb_attached_role_policies = iam_client.list_attached_role_policies(RoleName=kb_role_name)['AttachedPolicies']

    bedrock_agent_client.delete_knowledge_base(knowledgeBaseId=kb_id)
    aoss_client.delete_collection(id=collection['createCollectionDetail']['id'])
    aoss_client.delete_access_policy(type="data", name=access_policy['accessPolicyDetail']['name'])
    aoss_client.delete_security_policy(type="network", name=network_policy['securityPolicyDetail']['name'])
    aoss_client.delete_security_policy(type="encryption", name=encryption_policy['securityPolicyDetail']['name'])

    for policy in kb_attached_role_policies:
        iam_client.detach_role_policy(RoleName=kb_role_name, PolicyArn=policy['PolicyArn'])
        iam_client.delete_policy(PolicyArn=policy['PolicyArn'])

    iam_client.delete_role(RoleName=kb_role_name)
