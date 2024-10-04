import json
# import csv
from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.common.by import By  # Make sure to import By
import boto3
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC

# AWS Credentials (replace with your actual credentials)
aws_access_key_id = 'AKIAS2VS4CX5YIXSSAWX'
aws_secret_access_key = 'PunPGF7I+cw9P4MMayD0fguB59XGjE1xhqxjn996'
aws_region = 'us-east-1'  # e.g., 'us-east-1'

# Create an S3 client with embedded credentials
s3_client = boto3.client(
    's3',
    aws_access_key_id=aws_access_key_id,
    aws_secret_access_key=aws_secret_access_key,
    region_name=aws_region
)

def scrape_and_store():
    # Selenium setup for headless Chrome browser
    chrome_options = Options()
    chrome_options.add_argument("--ignore-certificate-errors")
    chrome_options.add_argument("--no-sandbox")
    chrome_options.add_argument("--disable-dev-shm-usage")
    
    driver = webdriver.Chrome(options=chrome_options)

    # Scrape the target URL
    url = 'https://www.vlr.gg/stats'
    driver.get(url)

    # Wait for the table to load
    try:
        WebDriverWait(driver, 20).until(EC.presence_of_element_located((By.TAG_NAME, 'table')))
        print("Page loaded successfully")
    except:
        print("Page loading timeout or element not found")

    # Locate the table
    table = driver.find_element(By.TAG_NAME, 'table')

    # Extract headers
    headers = []
    header_row = table.find_element(By.TAG_NAME, 'thead')  # Use 'thead' if available; otherwise, use 'tr'
    header_cells = header_row.find_elements(By.TAG_NAME, 'th')
    headers = [header.text for header in header_cells]
    
    print(f"Headers: {headers}")  # Debug: print headers

    # Extract data rows
    rows = table.find_elements(By.TAG_NAME, 'tr')

    data = []

    # Loop through each row and extract cell data
    for row in rows[1:]:  # Skip the first row if it is the header
        cells = row.find_elements(By.TAG_NAME, 'td')
        row_data = [cell.text for cell in cells]
        
        # Store row data if it has content (i.e., not an empty row)
        if row_data:
            data.append(row_data)

    # Combine headers and data
    combined_data = {"headers": headers, "rows": data}

    # Convert the data to JSON
    json_data = json.dumps(combined_data, indent=4)

    driver.quit()

    # Store the JSON data in S3
    s3_client.put_object(
        Bucket='vlrscraperbucket',
        Key='scraped-data.json',
        Body=json_data,
        ContentType='application/json'
    )

    print("Data successfully scraped and uploaded to S3 as JSON!")
    # print(json_data)  # Debug: print JSON data




def read_data_from_s3():
    # S3 Details (replace with your bucket name and object key)
    bucket_name = 'vlrscraperbucket'
    object_key = 'scraped-data.json'
    # Get the object from S3
    response = s3_client.get_object(Bucket=bucket_name, Key=object_key)
    
    # Read the content of the object
    data = response['Body'].read().decode('utf-8')
    
    # Print the content
    print("Data from S3:")
    print(data)

if __name__ == "__main__":
    scrape_and_store()
    read_data_from_s3()