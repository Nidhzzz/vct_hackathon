import csv
import json
from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.common.by import By
import boto3
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from io import StringIO
import os
import time

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

    player_data = []

    # Extract the rows' count beforehand
    table = driver.find_element(By.TAG_NAME, 'table')
    row_count = len(table.find_elements(By.TAG_NAME, 'tr'))

    for row_index in range(1, row_count):  # Skip header row
        try:
            # Re-locate table and rows each time to avoid stale elements
            table = driver.find_element(By.TAG_NAME, 'table')
            rows = table.find_elements(By.TAG_NAME, 'tr')
            cells = rows[row_index].find_elements(By.TAG_NAME, 'td')

            player_info = {}
            for i, cell in enumerate(cells):
                # Special handling for the 'PLAYER' column to get the player profile URL
                if "PLAYER" in cell.get_attribute('outerHTML').upper():
                    player_name = cell.text.strip()
                    player_url = cell.find_element(By.TAG_NAME, 'a').get_attribute('href')
                    player_info['player_name'] = player_name
                    player_info['player_url'] = player_url

                # Handle 'AGENTS' column for agents played
                elif "AGENTS" in cell.get_attribute('outerHTML').upper():
                    agent_imgs = cell.find_elements(By.TAG_NAME, 'img')
                    agent_names = [img.get_attribute('src').split('/agents/')[1].split('.png')[0] for img in agent_imgs]
                    player_info['agents'] = ', '.join(agent_names)
                else:
                    header = table.find_element(By.XPATH, f"//thead//th[{i + 1}]").text.strip()
                    player_info[header] = cell.text

            # Navigate to the player's profile page and collect detailed stats
            driver.get(player_info['player_url'])
            WebDriverWait(driver, 20).until(EC.presence_of_element_located((By.CLASS_NAME, 'player-header')))

            # Extract additional details from the player's profile page (example selectors)
            try:
                # Extract region/country
                region_element = driver.find_element(By.XPATH, "//div[@class='ge-text-light']")
                player_region = region_element.text.strip().split("\n")[-1]
                player_info['region'] = player_region
                print(f'Player Region: {player_region}')

                # Extract agent-specific stats from player's profile
                agent_stats = []
                agent_rows = driver.find_elements(By.CSS_SELECTOR, '.wf-table tbody tr')
                for agent_row in agent_rows:
                    cells = agent_row.find_elements(By.TAG_NAME, 'td')
                    agent_name = cells[0].text.strip()
                    acs = cells[3].text.strip()  # Adjust index based on structure (ACS column)
                    kd = cells[4].text.strip()  # Adjust index for K:D
                    agent_stats.append({'agent_name': agent_name, 'acs': acs, 'kd': kd})
                
                player_info['detailed_agent_stats'] = agent_stats

                # Extract current and past teams
                current_team_element = driver.find_element(By.CLASS_NAME, 'wf-module-item')
                current_team_name = current_team_element.text.strip()
                current_team_url = current_team_element.get_attribute('href')
                player_info['current_team'] = current_team_name
                player_info['current_team_url'] = current_team_url

                # Extract past teams
                past_team_elements = driver.find_elements(By.CLASS_NAME, 'wf-module-item')
                past_teams = []
                for team_element in past_team_elements:
                    past_team_name = team_element.text.strip()
                    past_team_url = team_element.get_attribute('href')
                    past_teams.append({'name': past_team_name, 'url': past_team_url})
                player_info['past_teams'] = past_teams

            except Exception as e:
                print(f"Error extracting details for {player_info['player_name']}: {str(e)}")

            # Go back to the main page
            driver.get(url)
            WebDriverWait(driver, 20).until(EC.presence_of_element_located((By.TAG_NAME, 'table')))
            time.sleep(1)  # Wait briefly to ensure page stability before continuing

        except Exception as e:
            print(f"Error processing row {row_index}: {str(e)}")

        player_data.append(player_info)

    # Save the data to a JSON file
    json_filename = 'players_data.json'
    with open(json_filename, 'w', encoding='utf-8') as f:
        json.dump(player_data, f, ensure_ascii=False, indent=4)

    print(f"Data successfully saved to {json_filename}")
    
    driver.quit()

    # Upload the JSON file to S3
    with open(json_filename, 'rb') as file:
        s3_client.put_object(
            Bucket='vlrscraperbucket',
            Key=json_filename,
            Body=file,
            ContentType='application/json'
        )

    print("JSON file successfully uploaded to S3!")

def read_data_from_s3():
    # S3 Details (replace with your bucket name and object key)
    bucket_name = 'vlrscraperbucket'
    object_key = 'players_data.json'
    
    # Get the object from S3
    response = s3_client.get_object(Bucket=bucket_name, Key=object_key)
    
    # Read the content of the object as a string
    data = response['Body'].read().decode('utf-8')
    
    # Load the content as JSON
    player_data = json.loads(data)
    
    # Print the content
    print("Data from S3 (JSON format):")
    for player in player_data:
        print(player)

if __name__ == "__main__":
    scrape_and_store()
    read_data_from_s3()
