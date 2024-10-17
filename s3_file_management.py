import boto3
from botocore.exceptions import ClientError

def check_and_create_bucket(s3_client, bucket_name, region_name):
    try:
        s3_client.head_bucket(Bucket=bucket_name)
        print(f'Bucket {bucket_name} Exists')
    except ClientError:
        print(f'Creating bucket {bucket_name}')
        if region_name == "us-east-1":
            s3_client.create_bucket(Bucket=bucket_name)
        else:
            s3_client.create_bucket(Bucket=bucket_name, CreateBucketConfiguration={'LocationConstraint': region_name})

def list_files_in_bucket(s3_client, bucket_name):
    file_info = []
    try:
        response = s3_client.list_objects_v2(Bucket=bucket_name)
        if 'Contents' in response:
            for obj in response['Contents']:
                print(obj['Key'])
                file_info.append(obj['Key'])
        else:
            print(f"No files found in bucket {bucket_name}.")
    except ClientError as e:
        print(f"Error listing files: {str(e)}")
    return file_info
