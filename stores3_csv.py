import csv
from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.common.by import By
import boto3
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from io import StringIO
import os

# AWS Credentials (replace with your actual credentials)
aws_access_key_id = os.getenv('AWS_ACCESS_KEY_ID')
aws_secret_access_key = os.getenv('AWS_SECRET_ACCESS_KEY')
aws_region = 'us-east-1'

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
    header_row = table.find_element(By.TAG_NAME, 'thead')
    header_cells = header_row.find_elements(By.TAG_NAME, 'th')
    headers = [header.text for header in header_cells]
    
    print(f"Headers: {headers}")

    # Extract data rows
    rows = table.find_elements(By.TAG_NAME, 'tr')

    data = []

    # Loop through each row and extract cell data
    for row in rows[1:]:  # Skip the first row if it is the header
        cells = row.find_elements(By.TAG_NAME, 'td')
        
        row_data = []
        for i, cell in enumerate(cells):
            # Special handling for the 'AGENTS' column
            if headers[i].strip().upper() == 'AGENTS':
                # Extract agent images from the cell
                agent_imgs = cell.find_elements(By.TAG_NAME, 'img')
                
                # Extract agent names from the 'src' attribute
                agent_names = []
                for img in agent_imgs:
                    src = img.get_attribute('src')
                    # Extract the agent name from the URL
                    if src:
                        agent_name = src.split('/agents/')[1].split('.png')[0]
                        agent_names.append(agent_name)

                # Join agent names as a comma-separated string
                row_data.append(', '.join(agent_names))
            else:
                row_data.append(cell.text)

        # Store row data if it has content
        if row_data:
            data.append(row_data)

    # Write the data to a CSV file
    csv_filename = 'scraped-data.csv'
    with open(csv_filename, mode='w', newline='', encoding='utf-8') as file:
        writer = csv.writer(file)
        writer.writerow(headers)  # Write headers
        writer.writerows(data)     # Write data rows

    print(f"Data successfully saved to {csv_filename}")

    driver.quit()

    # Read the CSV file to upload it to S3
    with open(csv_filename, 'rb') as file:
        s3_client.put_object(
            Bucket='vlrscraperbucket',
            Key=csv_filename,
            Body=file,
            ContentType='text/csv'
        )

    print("CSV file successfully uploaded to S3!")

def read_data_from_s3():
    # S3 Details (replace with your bucket name and object key)
    bucket_name = 'vlrscraperbucket'
    object_key = 'scraped-data.csv'
    
    # Get the object from S3
    response = s3_client.get_object(Bucket=bucket_name, Key=object_key)
    
    # Read the content of the object as a string
    data = response['Body'].read().decode('utf-8')
    
    # Use csv.reader to read the content as CSV
    csv_content = StringIO(data)
    csv_reader = csv.reader(csv_content)
    
    # Print the content
    print("Data from S3 (CSV format):")
    for row in csv_reader:
        print(row)

if __name__ == "__main__":
    scrape_and_store()
    read_data_from_s3()
