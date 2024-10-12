import boto3
import json

# AWS Setup with explicit region
boto3_session = boto3.session.Session(region_name='us-east-1')  # Set your preferred region
iam_client = boto3_session.client('iam')
sts_client = boto3.client('sts')
account_number = sts_client.get_caller_identity().get('Account')
region_name = boto3_session.region_name or 'us-east-1'  # Fallback to us-east-1 if region_name is None

def get_existing_policy_arn(policy_name):
    try:
        response = iam_client.get_policy(PolicyArn=f"arn:aws:iam::{account_number}:policy/{policy_name}")
        return response['Policy']['Arn']
    except iam_client.exceptions.NoSuchEntityException:
        return None

def get_existing_role(role_name):
    try:
        response = iam_client.get_role(RoleName=role_name)
        return response['Role']
    except iam_client.exceptions.NoSuchEntityException:
        return None

def create_bedrock_execution_role(bucket_name, fm_policy_name, s3_policy_name, bedrock_execution_role_name):
    # Foundation model policy
    foundation_model_policy_document = {
        "Version": "2012-10-17",
        "Statement": [
            {
                "Effect": "Allow",
                "Action": [
                    "bedrock:InvokeModel",
                ],
                "Resource": [
                    f"arn:aws:bedrock:{region_name}:{account_number}:foundation-model/amazon.titan-embed-text-v1"
                ]
            }
        ]
    }

    # Log the foundation model policy document
    print(f"Foundation Model Policy Document: {json.dumps(foundation_model_policy_document, indent=2)}")

    # S3 policy document
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

    # Log the S3 policy document
    print(f"S3 Policy Document: {json.dumps(s3_policy_document, indent=2)}")

    # Assume role policy
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
        # Create or get foundation model policy
        fm_policy_arn = get_existing_policy_arn(fm_policy_name)
        if fm_policy_arn is None:
            fm_policy = iam_client.create_policy(
                PolicyName=fm_policy_name,
                PolicyDocument=json.dumps(foundation_model_policy_document),
                Description='Policy for accessing foundation model',
            )
            fm_policy_arn = fm_policy["Policy"]["Arn"]
        else:
            print(f"Foundation model policy {fm_policy_name} already exists, skipping creation.")

    except Exception as e:
        print(f"Error creating foundation model policy: {str(e)}")
        return None

    try:
        # Create or get S3 policy
        s3_policy_arn = get_existing_policy_arn(s3_policy_name)
        if s3_policy_arn is None:
            s3_policy = iam_client.create_policy(
                PolicyName=s3_policy_name,
                PolicyDocument=json.dumps(s3_policy_document),
                Description='Policy for reading documents from S3',
            )
            s3_policy_arn = s3_policy["Policy"]["Arn"]
        else:
            print(f"S3 policy {s3_policy_name} already exists, skipping creation.")

    except Exception as e:
        print(f"Error creating S3 policy: {str(e)}")
        return None

    try:
        # Check if the role already exists
        bedrock_kb_execution_role = get_existing_role(bedrock_execution_role_name)
        if bedrock_kb_execution_role is None:
            # Create Bedrock execution role
            bedrock_kb_execution_role = iam_client.create_role(
                RoleName=bedrock_execution_role_name,
                AssumeRolePolicyDocument=json.dumps(assume_role_policy_document),
                Description='Amazon Bedrock Knowledge Base Execution Role for accessing OSS and S3',
                MaxSessionDuration=3600
            )
            print(f"Created Bedrock execution role {bedrock_execution_role_name}.")
            bedrock_kb_execution_role_arn = bedrock_kb_execution_role['Role']['Arn']
        else:
            print(f"Bedrock execution role {bedrock_execution_role_name} already exists, skipping creation.")
            bedrock_kb_execution_role_arn = bedrock_kb_execution_role['Arn']  # Correct way to get the ARN for an existing role

        # Attach policies to Amazon Bedrock execution role
        iam_client.attach_role_policy(
            RoleName=bedrock_execution_role_name,
            PolicyArn=fm_policy_arn
        )
        iam_client.attach_role_policy(
            RoleName=bedrock_execution_role_name,
            PolicyArn=s3_policy_arn
        )

        return bedrock_kb_execution_role_arn  # Return the role ARN instead of the entire role

    except Exception as e:
        print(f"Failed to create Bedrock execution role: {str(e)}")
        return None
