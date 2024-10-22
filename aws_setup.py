import boto3
import json
from botocore.exceptions import ClientError

# Initialize session and clients
boto3_session = boto3.session.Session(region_name='us-east-1')  # Set your preferred region
iam_client = boto3_session.client('iam')
sts_client = boto3.client('sts')
account_number = sts_client.get_caller_identity().get('Account')
region_name = boto3_session.region_name or 'us-east-1'

# Function to get the existing policy ARN
def get_existing_policy_arn(policy_name):
    try:
        response = iam_client.get_policy(PolicyArn=f"arn:aws:iam::{account_number}:policy/{policy_name}")
        return response['Policy']['Arn']
    except iam_client.exceptions.NoSuchEntityException:
        return None

# Function to get an existing IAM role
def get_existing_role(role_name):
    try:
        response = iam_client.get_role(RoleName=role_name)
        return response['Role']
    except iam_client.exceptions.NoSuchEntityException:
        return None

# Function to delete the oldest non-default version of a policy
def delete_oldest_policy_version(policy_arn):
    try:
        # Get all versions of the policy
        response = iam_client.list_policy_versions(PolicyArn=policy_arn)
        versions = response['Versions']

        # Find the oldest non-default version
        non_default_versions = [v for v in versions if not v['IsDefaultVersion']]
        if non_default_versions:
            oldest_version = sorted(non_default_versions, key=lambda x: x['CreateDate'])[0]
            print(f"Deleting oldest policy version: {oldest_version['VersionId']}")
            iam_client.delete_policy_version(
                PolicyArn=policy_arn,
                VersionId=oldest_version['VersionId']
            )
        else:
            print("No non-default versions to delete.")
    except ClientError as e:
        print(f"Error deleting oldest policy version: {str(e)}")

# Function to create or update a policy
def create_or_update_policy(policy_name, policy_document, description):
    policy_arn = get_existing_policy_arn(policy_name)
    if policy_arn is None:
        print(f"Creating new policy: {policy_name}")
        policy = iam_client.create_policy(
            PolicyName=policy_name,
            PolicyDocument=json.dumps(policy_document),
            Description=description,
        )
        policy_arn = policy["Policy"]["Arn"]
    else:
        # Check if there are 5 versions and delete the oldest if necessary
        response = iam_client.list_policy_versions(PolicyArn=policy_arn)
        if len(response['Versions']) >= 5:
            delete_oldest_policy_version(policy_arn)

        print(f"Updating existing policy: {policy_name}")
        iam_client.create_policy_version(
            PolicyArn=policy_arn,
            PolicyDocument=json.dumps(policy_document),
            SetAsDefault=True
        )
    return policy_arn

# Function to create or update the Bedrock execution role
def create_bedrock_execution_role(bucket_name, fm_policy_name, s3_policy_name, bedrock_execution_role_name):
    # Define the foundation model policy with OpenSearch permissions
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

    # Define the S3 access policy
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
                ]
            }
        ]
    }

    # Define the assume role policy for Bedrock
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

    try:
        # Create or update the foundation model policy
        fm_policy_arn = create_or_update_policy(fm_policy_name, foundation_model_policy_document, 'Policy for accessing foundation model and OpenSearch')

        # Create or update the S3 policy
        s3_policy_arn = create_or_update_policy(s3_policy_name, s3_policy_document, 'Policy for reading documents from S3')

        # Check or create the Bedrock execution role
        bedrock_kb_execution_role = get_existing_role(bedrock_execution_role_name)
        if bedrock_kb_execution_role is None:
            # Create the role if it does not exist
            bedrock_kb_execution_role = iam_client.create_role(
                RoleName=bedrock_execution_role_name,
                AssumeRolePolicyDocument=json.dumps(assume_role_policy_document),
                Description='Amazon Bedrock Knowledge Base Execution Role for accessing OpenSearch and S3',
                MaxSessionDuration=3600
            )
            print(f"Created Bedrock execution role {bedrock_execution_role_name}.")
            bedrock_kb_execution_role_arn = bedrock_kb_execution_role['Role']['Arn']
        else:
            print(f"Bedrock execution role {bedrock_execution_role_name} already exists, skipping creation.")
            bedrock_kb_execution_role_arn = bedrock_kb_execution_role['Arn']

        # Attach the policies to the execution role
        attach_policy_to_role(bedrock_execution_role_name, fm_policy_arn, s3_policy_arn)

    except ClientError as e:
        print(f"Error: {str(e)}")
    
    return bedrock_kb_execution_role_arn  # Return the ARN regardless of success or failure

# Function to attach policies to the execution role
def attach_policy_to_role(role_name, fm_policy_arn, s3_policy_arn):
    try:
        attached_policies = iam_client.list_attached_role_policies(RoleName=role_name)['AttachedPolicies']
        attached_policy_arns = [policy['PolicyArn'] for policy in attached_policies]

        if fm_policy_arn not in attached_policy_arns:
            iam_client.attach_role_policy(
                RoleName=role_name,
                PolicyArn=fm_policy_arn
            )

        if s3_policy_arn not in attached_policy_arns:
            iam_client.attach_role_policy(
                RoleName=role_name,
                PolicyArn=s3_policy_arn
            )

        print(f"Policies attached to role {role_name}.")
    except ClientError as e:
        print(f"Failed to attach policies to role {role_name}: {str(e)}")
