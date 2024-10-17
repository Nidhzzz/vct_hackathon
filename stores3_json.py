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

def save_data_locally(data, file_name='vct_players_data.json'):
    # Convert data to JSON string
    with open(file_name, 'w') as file:
        json.dump(data, file, indent=4)
    print(f"Data successfully saved locally as {file_name}")

def upload_to_s3(file_name, bucket_name, object_key):
    # Upload the local file to S3
    with open(file_name, 'rb') as data:
        s3_client.put_object(
            Bucket=bucket_name,
            Key=object_key,
            Body=data
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
                try:
                    realname_element = driver.find_element(By.XPATH, "//h2[@class='player-real-name ge-text-light']")
                    player_realname = realname_element.text.strip()
                    player_info["player_profile"]['real_name'] = player_realname
                except Exception as e:
                    print(f"Error extracting real name: {str(e)}")
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
                    # Locate the container for current teams specifically
                    current_team_container = driver.find_element(By.XPATH, "//h2[contains(text(),'Current Teams')]/following-sibling::div[@class='wf-card']")
                    # Find all individual team items
                    current_team_items = current_team_container.find_elements(By.CSS_SELECTOR, "a.wf-module-item")

                    # Check if there's any team in the current teams section
                    if current_team_items:
                        current_team_element = current_team_items[0]  # Assuming there's only one current team
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
                    else:
                        # If no current team is found, set current team to empty
                        player_info["history"]["current_team"] = {}

                except Exception as e:
                    # If no current team section is found or another error occurs, set current team to empty
                    player_info["history"]["current_team"] = {}
                    print(f"Error extracting current team: {str(e)}")


                # Extract past team details
                try:
                    # Locate the container for past teams
                    past_teams_container = driver.find_element(By.XPATH, "//h2[contains(text(),'Past Teams')]/following-sibling::div[@class='wf-card']")
                    # Find all individual team items
                    past_team_items = past_teams_container.find_elements(By.CSS_SELECTOR, "a.wf-module-item")

                    # Extract details from each past team
                    for team_element in past_team_items:
                        try:
                            # Extract team name
                            team_name_element = team_element.find_element(By.XPATH, ".//div[@style='font-weight: 500;']")
                            team_name = team_name_element.text.strip() if team_name_element else "Unknown"

                            # Extract duration and replace Unicode em dash with a hyphen
                            team_duration_elements = team_element.find_elements(By.XPATH, ".//div[@class='ge-text-light']")
                            team_duration = team_duration_elements[-1].text.strip().replace("\u2013", "-")

                            # Extract team URL
                            team_url = team_element.get_attribute('href')
                            try:
                                team_id = team_url.split('/team/')[1].split('/')[0] 
                            except IndexError:
                                team_id = "Unknown"

                            # Append each team as a separate dictionary to the "past_teams" list
                            player_info["history"]["past_teams"].append({
                                "team_id": team_id,
                                "name": team_name,
                                "duration": team_duration,
                                "url": team_url
                            })

                        except Exception as e:
                            print(f"Could not extract past team details properly: {str(e)}")

                except Exception as e:
                    print(f"Error extracting past teams for {player_info['player_profile']['player_name']}: {str(e)}")

                # Extract event placements
                try:
                    # Locate the container for event placements
                    event_placements_container = driver.find_element(By.XPATH, "//h2[contains(text(),'Event Placements')]/following-sibling::div[@class='wf-card']")
                    # Find all individual event items
                    event_items = event_placements_container.find_elements(By.XPATH, ".//a[contains(@class, 'player-event-item')]")

                    # Extract details from each event placement
                    for event_element in event_items:
                        try:
                            # Extract event name combined details
                            event_combined_details = event_element.text.strip()
                            event_url = event_element.get_attribute('href')
                            try:
                                event_id = event_url.split('/event/')[1].split('/')[0]  
                            except IndexError:
                                event_id = "Unknown"

                            # Split the combined details into lines
                            details_lines = event_combined_details.split("\n")

                            # Extract the relevant details based on the line structure
                            if len(details_lines) >= 3:
                                tournament_name = details_lines[0]
                                position = details_lines[1].replace("\u2013", "-")  # Reformatting the hyphen
                                winnings_full = details_lines[2]

                                # Enhanced Parsing Logic
                                # Use regex to identify winnings amount
                                match = re.search(r"(\$[\d,]+)", winnings_full)
                                if match:
                                    winnings_amount = match.group(1).replace(",", "")
                                    # Extract the team name by removing the winnings amount
                                    with_team = winnings_full.replace(winnings_amount, "").strip()

                                    # Handle cases like "$1316 BBL Queens" where winnings and team are combined
                                    if with_team.startswith("$"):
                                        # Split the string further to isolate the winnings and team
                                        parts = with_team.split(" ", 1)
                                        winnings_amount = parts[0].replace(",", "")
                                        with_team = parts[1] if len(parts) > 1 else ""

                                else:
                                    winnings_amount = ""
                                    with_team = winnings_full.strip()

                            else:
                                tournament_name = details_lines[0]
                                position = winnings_amount = with_team = ""  # Default if not all details are present

                            # Append the extracted details into the player's tournament history
                            player_info["history"]["tournaments"].append({
                                "event_id": event_id,
                                "tournament_name": tournament_name,
                                "position": position,
                                "winnings": winnings_amount,
                                "with_team": with_team,
                                "url": event_url
                            })

                        except Exception as e:
                            print(f"Could not extract event placement details properly: {str(e)}")

                except Exception as e:
                    print(f"Error extracting event placements for {player_info['player_profile']['player_name']}: {str(e)}")

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

    # Save the data locally first
    local_file_name = 'vct_players_data.json'
    save_data_locally(players_data, file_name=local_file_name)

    # Then upload the saved file to S3
    upload_to_s3(file_name=local_file_name, bucket_name='vlrscraperbucket', object_key=local_file_name)


if __name__ == "__main__":
    scrape_and_store()
