import boto3
import pandas as pd
from io import StringIO
import os

# AWS Credentials (replace with your actual credentials)
aws_access_key_id = os.getenv('AWS_ACCESS_KEY_ID')
aws_secret_access_key = os.getenv('AWS_SECRET_ACCESS_KEY')
aws_region = 'us-east-1'

# Create an S3 client
s3_client = boto3.client(
    's3',
    aws_access_key_id=aws_access_key_id,
    aws_secret_access_key=aws_secret_access_key,
    region_name=aws_region
)

# S3 bucket and file details
bucket_name = 'vlrscraperbucket'
object_key = 'scraped-data.csv'  # Replace with the name of your S3 CSV file

def load_data_from_s3(bucket_name, object_key):
    # Get the CSV object from S3
    response = s3_client.get_object(Bucket=bucket_name, Key=object_key)
    
    # Read the CSV content from the S3 response
    csv_data = response['Body'].read().decode('utf-8')
    
    # Load the CSV data into a Pandas DataFrame
    df = pd.read_csv(StringIO(csv_data))
    
    return df

# Load the data
df = load_data_from_s3(bucket_name, object_key)

# Example of working with the DataFrame
print(df.head())  # Display the first few rows

# Perform cleaning and transformation if needed
df['PLAYER'] = df['PLAYER'].str.replace('\n', ' ')  # Clean PLAYER column

# Example analysis
print(df.describe())

# Plot data or further processing as needed
