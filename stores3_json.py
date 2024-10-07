import csv
import json
import time
from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.common.by import By
from selenium.common.exceptions import StaleElementReferenceException
import boto3
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from io import StringIO
import os
import regex as re

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

def upload_to_s3(data, bucket_name, object_key):
    # Convert data to JSON string
    json_data = json.dumps(data, indent=4)
    
    # Upload the JSON string to S3
    s3_client.put_object(
        Bucket=bucket_name,
        Key=object_key,
        Body=json_data
    )
    print(f"Data successfully uploaded to S3: s3://{bucket_name}/{object_key}")

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
    except:
        print("Page loading timeout or element not found")

    # Extract headers
    table = driver.find_element(By.TAG_NAME, 'table')
    headers = [header.text for header in table.find_elements(By.TAG_NAME, 'thead')[0].find_elements(By.TAG_NAME, 'th')]

    players_data = []

    # Iterate through row indices to avoid stale references
    row_index = 1
    while True:  # Remove row limit to scrape all records
        try:
            # Refresh the list of rows to avoid stale references
            table = driver.find_element(By.TAG_NAME, 'table')
            rows = table.find_elements(By.TAG_NAME, 'tr')

            if row_index >= len(rows):
                break

            row = rows[row_index]

            # Retry mechanism for stale element
            for attempt in range(3):
                try:
                    cells = row.find_elements(By.TAG_NAME, 'td')
                    break  # Break loop if successful
                except StaleElementReferenceException:
                    time.sleep(2)
                    # Refresh rows in case of stale reference
                    table = driver.find_element(By.TAG_NAME, 'table')
                    rows = table.find_elements(By.TAG_NAME, 'tr')
                    row = rows[row_index]

                    if attempt == 2:
                        raise

            player_info = {
                "player_profile": {},
                "statistics": {
                    "agents": [],
                    "performance": {}
                },
                "history": {
                    "current_team": {},
                    "past_teams": [],
                    "tournaments": []
                }
            }
            
            for i, cell in enumerate(cells):
                header = headers[i].strip().upper()

                # Special handling for the 'PLAYER' column to get the player profile URL
                if header == 'PLAYER':
                    combined_name = cell.text.strip()
                    player_url = cell.find_element(By.TAG_NAME, 'a').get_attribute('href')
                    
                    # Extract player_id from the player URL
                    try:
                        player_id = player_url.split('/player/')[1].split('/')[0]
                        player_info["player_profile"]["player_id"] = player_id
                    except IndexError:
                        player_info["player_profile"]["player_id"] = "Unknown"
                    
                    # Split player name and team from the combined name
                    if "\n" in combined_name:
                        player_name, team = combined_name.split("\n", 1)
                    else:
                        player_name, team = combined_name, "Unknown"

                    # Store player name, team, and URL
                    player_info["player_profile"]["player_name"] = player_name
                    player_info["player_profile"]["team"] = team
                    player_info["player_profile"]["player_url"] = player_url

                # Handle 'AGENTS' column for agents played
                elif header == 'AGENTS':
                    agent_imgs = cell.find_elements(By.TAG_NAME, 'img')
                    agent_names = []

                    # Extract agent names from either 'alt' or 'src'
                    for img in agent_imgs:
                        agent_name = img.get_attribute('alt')
                        if not agent_name:
                            # Fallback to 'src' if 'alt' is not present
                            src = img.get_attribute('src')
                            if src:
                                try:
                                    agent_name = src.split('/agents/')[1].split('.png')[0]
                                except IndexError:
                                    agent_name = None
                        
                        if agent_name:
                            agent_names.append({"agent_name": agent_name})

                    player_info["statistics"]["agents"] = agent_names

                # Add performance metrics to the "performance" section
                else:
                    performance_metric = cell.text.strip()
                    player_info["statistics"]["performance"][header] = performance_metric

            # Navigate to the player's profile page and collect detailed stats
            driver.get(player_info["player_profile"]["player_url"])
            try:
                WebDriverWait(driver, 20).until(EC.presence_of_element_located((By.CLASS_NAME, 'player-header')))

                # Extract region/country
                try:
                    region_element = driver.find_element(By.XPATH, "//div[@class='ge-text-light']")
                    player_region = region_element.text.strip().split("\n")[-1]
                    player_info["player_profile"]['region'] = player_region
                except Exception as e:
                    print(f"Error extracting region: {str(e)}")

                # Extract agent-specific stats from player's profile
                agent_stats = []
                agents_table = driver.find_element(By.XPATH, "//table[@class='wf-table']")
                agent_rows = agents_table.find_elements(By.TAG_NAME, 'tr')
                
                for agent_row in agent_rows:
                    cells = agent_row.find_elements(By.TAG_NAME, 'td')
                    if len(cells) >= 11:  # Ensure sufficient columns are present
                        agent_name = cells[0].find_element(By.TAG_NAME, 'img').get_attribute('alt')
                        usage = cells[1].text.strip()
                        rnd = cells[2].text.strip()
                        rating = cells[3].text.strip()
                        acs = cells[4].text.strip()
                        kd = cells[5].text.strip()
                        adr = cells[6].text.strip()
                        kast = cells[7].text.strip()
                        kpr = cells[8].text.strip()
                        apr = cells[9].text.strip()
                        fkpr = cells[10].text.strip()
                        fdpr = cells[11].text.strip()
                        k = cells[12].text.strip()
                        d = cells[13].text.strip()
                        a = cells[14].text.strip()
                        fk = cells[15].text.strip()
                        fd = cells[16].text.strip()
                        
                        agent_stats.append({
                            'agent_name': agent_name,
                            'usage': usage,
                            'rating': rating,
                            'RND': rnd,
                            'ACS': acs,
                            'K:D': kd,
                            'ADR': adr,
                            'KAST': kast,
                            'KPR': kpr,
                            'APR': apr,
                            'FKPR': fkpr,
                            'FDPR': fdpr,
                            'k': k,
                            'd': d,
                            'a': a,
                            'fk': fk,
                            'fd': fd
                        })
                
                player_info["statistics"]["agents"] = agent_stats

                try:
                    # Extract current team details
                    current_team_element = driver.find_element(By.CLASS_NAME, 'wf-module-item')
                    team_name_duration = current_team_element.text.strip().split("\n")
                    
                    # Separate team name and duration
                    if len(team_name_duration) >= 2:
                        team_name = team_name_duration[0].strip()
                        duration = team_name_duration[1].strip()
                    else:
                        team_name = team_name_duration[0].strip()
                        duration = ""  # Default to empty string if duration not present

                    team_url = current_team_element.get_attribute('href')
                    
                    # Extract team_id from the team URL
                    try:
                        team_id = team_url.split('/team/')[1].split('/')[0]
                    except IndexError:
                        team_id = "Unknown"
                    
                    player_info["history"]["current_team"] = {
                        "name": team_name,
                        "duration": duration,
                        "url": team_url,
                        "team_id": team_id
                    }
                except Exception as e:
                    print(f"Error extracting current team: {str(e)}")

                # Additional details about past teams and events would go here (as in original logic)

            except Exception as e:
                print(f"Error navigating to player profile for {player_info['player_profile']['player_name']}: {str(e)}")

            players_data.append(player_info)
            row_index += 1

            # Go back to the main page to continue extracting the next player's data
            driver.get(url)
        
        except Exception as e:
            print(f"Error processing row index {row_index}: {str(e)}")
            break  # Break loop if there's an error in processing

    driver.quit()

    # Upload the complete data to S3
    upload_to_s3(players_data, bucket_name='vlrscraperbucket', object_key='players_data.json')

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
    # read_data_from_s3()
