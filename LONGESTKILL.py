import requests

# ===================== CONFIG =====================
API_KEY = "eyJ0eXAiOiJKV1QiLCJhbGciOiJIUzI1NiJ9.eyJqdGkiOiIyMThmZDc4MC1jOGFhLTAxM2QtMWI2Ni0wNjFhOWQ1YjYxYWYiLCJpc3MiOiJnYW1lbG9ja2VyIiwiaWF0IjoxNzM5MDYwNjYxLCJwdWIiOiJibHVlaG9sZSIsInRpdGxlIjoicHViZyIsImFwcCI6Ii0xODA1OTMzNy0wYTQ0LTQzZjYtYWE0OS01NTM4YmZhZjEzOTUifQ.p2ZG2vQW9Nrp73Iul77UmCLwKKlcsXLz2xSoO2EhsGA"
PLAYER_NAME = "Squidddy"
PLATFORM = "steam"  # steam, psn, xbox, kakao, stadia
# ==================================================
*
HEADERS = {
    "Authorization": f"Bearer {API_KEY}",
    "Accept": "application/vnd.api+json"
}

BASE_URL = f"https://api.pubg.com/shards/{PLATFORM}"


def get_player_id(player_name):
    url = f"{BASE_URL}/players?filter[playerNames]={player_name}"
    response = requests.get(url, headers=HEADERS)
    
    if response.status_code != 200:
        print(f"❌ Error fetching player: {response.status_code} - {response.text}")
        return None
    
    data = response.json()
    player_id = data["data"][0]["id"]
    print(f"✅ Found player: {player_name} | ID: {player_id}")
    return player_id


def get_longest_kills(player_id):
    url = f"{BASE_URL}/players/{player_id}/seasons/lifetime"
    response = requests.get(url, headers=HEADERS)
    
    if response.status_code != 200:
        print(f"❌ Error fetching stats: {response.status_code} - {response.text}")
        return
    
    data = response.json()
    game_modes = data["data"]["attributes"]["gameModeStats"]
    
    print("\n" + "="*50)
    print(f"🎯 LONGEST KILLS FOR: {PLAYER_NAME.upper()}")
    print("="*50)
    
    longest_overall = 0
    best_mode = ""
    
    for mode, stats in game_modes.items():
        longest = stats.get("longestKill", 0)
        print(f"  {mode:<20} → {longest:.2f}m")
        
        if longest > longest_overall:
            longest_overall = longest
            best_mode = mode
    
    print("="*50)
    print(f"🏆 ALL-TIME LONGEST KILL : {longest_overall:.2f}m  ({best_mode})")
    print("="*50)


if __name__ == "__main__":
    player_id = get_player_id(PLAYER_NAME)
    if player_id:
        get_longest_kills(player_id)