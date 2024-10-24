import json

# Function to format a player's performance into a paragraph
def format_player_paragraph(player):
    # Extract profile and team info
    player_name = player['player_profile']['player_name']
    team_name = player['player_profile']['team']
    region = player['player_profile']['region']
    
    # General performance
    performance = player['statistics']['performance']
    total_kills = performance['K']
    total_deaths = performance['D']
    total_assists = performance['A']
    k_d_ratio = performance['K:D']
    acs = performance['ACS']
    adr = performance['ADR']
    kast = performance['KAST']
    
    # Build a performance paragraph
    paragraph = f"{player_name}, from {region}, currently playing for {team_name}, had a strong showing with an overall ACS of {acs} and a K/D ratio of {k_d_ratio}. {player_name} contributed a total of {total_kills} kills, {total_deaths} deaths, and {total_assists} assists with an ADR of {adr}. Their KAST (Kill, Assist, Survive, Trade percentage) was {kast}%, demonstrating consistent involvement in team fights."

    # Agent-specific performance
    agent_performance_paragraphs = []
    for agent in player['statistics']['agents']:
        agent_name = agent['agent_name']
        agent_usage = agent['usage']
        agent_acs = agent['ACS']
        agent_k_d = agent['K:D']
        kills = agent['k']
        deaths = agent['d']
        assists = agent['a']
        adr = agent['ADR']
        fk = agent['fk']
        fd = agent['fd']

        agent_paragraph = (f"While playing {agent_name}, used in {agent_usage} of their matches, {player_name} achieved an ACS of {agent_acs}, "
                           f"with a K/D ratio of {agent_k_d}, securing {kills} kills and {deaths} deaths. {player_name} also managed {assists} assists, "
                           f"with an ADR of {adr}. They secured {fk} first kills while only conceding {fd} first deaths.")
        agent_performance_paragraphs.append(agent_paragraph)
    
    # Combine the general and agent-specific paragraphs
    full_paragraph = paragraph + "\n\n" + "\n\n".join(agent_performance_paragraphs)
    
    return full_paragraph

# Open and read the JSON file
with open('players_data.json', 'r') as file:
    data = json.load(file) 

# Print the data
print(format_player_paragraph(data[0]))