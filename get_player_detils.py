import requests
import json
from datetime import datetime
from collections import defaultdict


class PUBGMatchesFetcher:
    def __init__(self, api_key, platform='steam'):
        """
        Initialize PUBG API client

        Args:
            api_key: Your PUBG API key
            platform: Platform (steam, psn, xbox, kakao, stadia, etc.)
        """
        self.api_key = api_key
        self.platform = platform
        self.base_url = f"https://api.pubg.com/shards/{platform}"
        self.headers = {
            "Authorization": f"Bearer {api_key}",
            "Accept": "application/vnd.api+json"
        }

    # ─────────────────────────────────────────────
    #  CORE API CALLS
    # ─────────────────────────────────────────────

    def get_player_by_name(self, player_name):
        url = f"{self.base_url}/players"
        params = {"filter[playerNames]": player_name}
        try:
            r = requests.get(url, headers=self.headers, params=params)
            r.raise_for_status()
            data = r.json()
            if data.get('data'):
                return data['data'][0]
            print(f"Player '{player_name}' not found")
        except requests.exceptions.RequestException as e:
            print(f"Error fetching player: {e}")
        return None

    def get_match_details(self, match_id):
        url = f"{self.base_url}/matches/{match_id}"
        try:
            r = requests.get(url, headers=self.headers)
            r.raise_for_status()
            return r.json()
        except requests.exceptions.RequestException as e:
            print(f"Error fetching match {match_id}: {e}")
        return None

    def get_telemetry(self, telemetry_url):
        """Download and return telemetry event list from the asset URL."""
        try:
            r = requests.get(telemetry_url, headers={"Accept-Encoding": "gzip"}, timeout=30)
            r.raise_for_status()
            return r.json()
        except requests.exceptions.RequestException as e:
            print(f"  ⚠  Telemetry fetch failed: {e}")
        return []

    # ─────────────────────────────────────────────
    #  PARSING
    # ─────────────────────────────────────────────

    def parse_match_data(self, match_data):
        """Parse top-level match attributes."""
        if not match_data:
            return None
        attr = match_data['data']['attributes']
        created_at = datetime.fromisoformat(attr['createdAt'].replace('Z', '+00:00'))
        return {
            'match_id':        match_data['data']['id'],
            'created_at':      created_at.strftime('%Y-%m-%d %H:%M:%S UTC'),
            'duration_seconds': attr['duration'],
            'duration_minutes': round(attr['duration'] / 60, 2),
            'game_mode':       attr['gameMode'],
            'match_type':      attr['matchType'],
            'map_name':        attr['mapName'],
            'season_state':    attr.get('seasonState', 'N/A'),
            'is_custom_match': attr.get('isCustomMatch', False),
            'tags':            attr.get('tags'),
            'title_id':        attr.get('titleId'),
            'shard_id':        attr.get('shardId'),
            'patch_version':   attr.get('patchVersion'),
        }

    def parse_included(self, match_data):
        """
        Walk the 'included' array and return organised dicts:
            participants  → {participant_id: {...}}
            rosters       → [{rank, won, participant_ids:[...]}]
            telemetry_url → str | None
        """
        participants = {}
        rosters = []
        telemetry_url = None

        for item in match_data.get('included', []):
            t = item['type']

            if t == 'participant':
                s = item['attributes']['stats']
                participants[item['id']] = {
                    'participant_id':   item['id'],
                    'player_id':        s.get('playerId', ''),
                    'player_name':      s.get('name', ''),
                    # Combat
                    'kills':            s.get('kills', 0),
                    'kill_place':       s.get('killPlace', 0),
                    'headshot_kills':   s.get('headShotKills', 0),
                    'road_kills':       s.get('roadKills', 0),
                    'team_kills':       s.get('teamKills', 0),
                    'kill_streaks':     s.get('killStreaks', 0),
                    'longest_kill_m':   round(s.get('longestKill', 0), 2),
                    'damage_dealt':     round(s.get('damageDealt', 0), 2),
                    'assists':          s.get('assists', 0),
                    'dbnos':            s.get('DBNOs', 0),
                    'revives':          s.get('revives', 0),
                    # Survival
                    'survival_time_min': round(s.get('timeSurvived', 0) / 60, 2),
                    'death_type':       s.get('deathType', ''),
                    'rank':             s.get('winPlace', 0),
                    # Items
                    'heals_used':       s.get('heals', 0),
                    'boosts_used':      s.get('boosts', 0),
                    'weapons_acquired': s.get('weaponsAcquired', 0),
                    # Distance
                    'walk_distance_km': round(s.get('walkDistance', 0) / 1000, 2),
                    'ride_distance_km': round(s.get('rideDistance', 0) / 1000, 2),
                    'swim_distance_km': round(s.get('swimDistance', 0) / 1000, 2),
                    # Vehicles
                    'vehicle_destroys': s.get('vehicleDestroys', 0),
                }

            elif t == 'roster':
                attr = item['attributes']
                rosters.append({
                    'roster_id':       item['id'],
                    'rank':            attr['stats'].get('rank', 0),
                    'team_id':         attr['stats'].get('teamId', ''),
                    'won':             attr.get('won', 'false') == 'true',
                    'participant_ids': [p['id'] for p in item['relationships'].get('participants', {}).get('data', [])],
                })

            elif t == 'asset':
                telemetry_url = item['attributes'].get('URL')

        return participants, rosters, telemetry_url

    # ─────────────────────────────────────────────
    #  TELEMETRY PARSING
    # ─────────────────────────────────────────────

    # ─────────────────────────────────────────────
    #  WEAPON NAME LOOKUP
    # ─────────────────────────────────────────────

    WEAPON_NAMES = {
        # ARs
        'WeapM416_C':           'M416',
        'WeapHK416_C':          'M416 (HK416)',
        'WeapAK47_C':           'AKM',
        'WeapAK47_Decay_C':     'Beryl M762',
        'WeapG36C_C':           'G36C',
        'WeapSCARLight_C':      'SCAR-L',
        'WeapMk47Mutant_C':     'Mk47 Mutant',
        'WeapACE32_C':          'ACE32',
        'WeapQBZ95_C':          'QBZ95',
        'WeapFAL_C':            'SLR (FAL)',
        'WeapM16A4_C':          'M16A4',
        # DMRs / Snipers
        'WeapSKS_C':            'SKS',
        'WeapMini14_C':         'Mini 14',
        'WeapVSS_C':            'VSS',
        'WeapKar98k_C':         'Kar98k',
        'WeapM24_C':            'M24',
        'WeapAWM_C':            'AWM',
        'WeapMk14_C':           'Mk14 EBR',
        'WeapDragunov_C':       'SVD Dragunov',
        'WeapLynx_C':           'Lynx AMR',
        # SMGs
        'WeapUMP_C':            'UMP45',
        'WeapVector_C':         'Vector',
        'WeapThompson_C':       'Tommy Gun',
        'WeapMP5K_C':           'MP5K',
        'WeapBizonPP19_C':      'PP-19 Bizon',
        'WeapMP9_C':            'MP9',
        # Shotguns
        'WeapS686_C':           'S686',
        'WeapS1897_C':          'S1897',
        'WeapS12K_C':           'S12K',
        'WeapSaiga12_C':        'DBS',
        'WeapO12_C':            'O12',
        # LMGs
        'WeapM249_C':           'M249',
        'WeapDP28_C':           'DP-28',
        # Pistols
        'WeapG18_C':            'P18C',
        'WeapP1911_C':          'P1911',
        'WeapP92_C':            'P92',
        'WeapRevolver_C':       'R1895',
        'WeapR45_C':            'R45',
        'WeapDesertEagle_C':    'Desert Eagle',
        # Launchers / Special
        'WeapM79_C':            'M79 Grenade Launcher',
        'WeapRPG7_C':           'RPG-7',
        'WeapPanzerfaust_C':    'Panzerfaust',
        'WeapFlareGun_C':       'Flare Gun',
        'WeapCrossbow_C':       'Crossbow',
        'WeapZiplinegun_C':     'Zipline Gun',
        'WeapIntegratedRepair_C': 'Repair Gun',
        # Melee / Throwables
        'WeapPan_C':            'Pan',
        'WeapMachete_C':        'Machete',
        'WeapCowbar_C':         'Crowbar',
        'Grenade_C':            'Frag Grenade',
        'Molotov_C':            'Molotov',
        'Flashbang_C':          'Flashbang',
        'SmokeGrenade_C':       'Smoke Grenade',
        # Damage causes (zone / vehicles)
        'BlueZone':             'Blue Zone',
        'RedZone':              'Red Zone',
        'Bluezone':             'Blue Zone',
        'VehicleWheeledSmall':  'Vehicle (small)',
        'VehicleWheeled':       'Vehicle',
        'VehicleBoat':          'Boat',
    }

    def friendly_weapon(self, raw_name):
        """Return a human-readable weapon name, stripping Item_Weapon_ prefixes."""
        if not raw_name:
            return 'Unknown'
        # Strip common prefixes from item IDs
        clean = raw_name.replace('Item_Weapon_', '').replace('Item_', '')
        return self.WEAPON_NAMES.get(raw_name, self.WEAPON_NAMES.get(clean, clean))

    def parse_telemetry_for_player(self, events, player_name):
        """
        Extract from telemetry for a specific player:
          - kill events  (with weapon, distance, victim)
          - longest kill info
          - all weapons picked up
          - death event
          - damage taken event count
        """
        result = {
            'kills': [],
            'longest_kill': None,
            'weapons_picked_up': [],
            'death': None,
            'damage_taken_events': 0,
        }

        max_dist = -1

        for ev in events:
            ev_type = ev.get('_T', '')

            # ── Kill events ──────────────────────────────────────────
            if ev_type == 'LogPlayerKill':
                killer = ev.get('killer') or {}
                victim = ev.get('victim') or {}

                # Did our player make this kill?
                if killer.get('name', '') == player_name:
                    raw_weapon = ev.get('damageCauserName', 'Unknown')
                    distance   = round(ev.get('distance', 0) / 100, 2)   # cm → m
                    kill_info  = {
                        'victim':      victim.get('name', 'Unknown'),
                        'weapon_raw':  raw_weapon,
                        'weapon':      self.friendly_weapon(raw_weapon),
                        'distance_m':  distance,
                        'headshot':    ev.get('isHeadShot', False),
                        'timestamp':   ev.get('_D', ''),
                    }
                    result['kills'].append(kill_info)
                    if distance > max_dist:
                        max_dist = distance
                        result['longest_kill'] = kill_info

                # Was our player the victim?
                if victim.get('name', '') == player_name:
                    raw_weapon = ev.get('damageCauserName', 'Unknown')
                    result['death'] = {
                        'killed_by': killer.get('name', 'Zone/Environment'),
                        'weapon_raw': raw_weapon,
                        'weapon':    self.friendly_weapon(raw_weapon),
                        'timestamp': ev.get('_D', ''),
                    }

            # ── Item pickups ─────────────────────────────────────────
            elif ev_type == 'LogItemPickup':
                char = ev.get('character') or {}
                if char.get('name', '') == player_name:
                    item     = ev.get('item') or {}
                    category = item.get('category', '')
                    if category == 'Weapon':
                        raw_id = item.get('itemId', '')
                        result['weapons_picked_up'].append({
                            'item_id':   raw_id,
                            'name':      self.friendly_weapon(raw_id),
                            'timestamp': ev.get('_D', ''),
                        })

            # ── Damage taken ─────────────────────────────────────────
            elif ev_type == 'LogPlayerTakeDamage':
                victim = ev.get('victim') or {}
                if victim.get('name', '') == player_name:
                    result['damage_taken_events'] += 1

        return result

    # ─────────────────────────────────────────────
    #  HIGH-LEVEL
    # ─────────────────────────────────────────────

    def get_last_matches(self, player_name, num_matches=5, fetch_telemetry=True):
        player = self.get_player_by_name(player_name)
        if not player:
            return None

        player_id = player['id']
        match_ids = [rel['id'] for rel in player['relationships']['matches']['data']][:num_matches]

        print(f"Found {len(match_ids)} matches for '{player_name}'")
        print("Fetching match details...\n")

        all_matches = []

        for i, match_id in enumerate(match_ids, 1):
            print(f"[{i}/{len(match_ids)}] Match {match_id}")

            match_data = self.get_match_details(match_id)
            if not match_data:
                continue

            parsed_match           = self.parse_match_data(match_data)
            participants, rosters, telemetry_url = self.parse_included(match_data)

            # Find our player's participant entry
            my_participant = next(
                (p for p in participants.values() if p['player_id'] == player_id),
                None
            )

            # Build team info
            team_info = None
            if my_participant:
                pid = my_participant['participant_id']
                for roster in rosters:
                    if pid in roster['participant_ids']:
                        team_members = [
                            participants[pid2]
                            for pid2 in roster['participant_ids']
                            if pid2 in participants
                        ]
                        team_info = {
                            'team_rank': roster['rank'],
                            'team_won':  roster['won'],
                            'team_id':   roster['team_id'],
                            'teammates': [
                                {'name': m['player_name'], 'kills': m['kills'], 'damage': m['damage_dealt']}
                                for m in team_members if m['player_id'] != player_id
                            ],
                        }
                        break

            # Telemetry
            telemetry_info = None
            if fetch_telemetry and telemetry_url:
                print(f"  → Downloading telemetry...")
                events = self.get_telemetry(telemetry_url)
                if events and my_participant:
                    telemetry_info = self.parse_telemetry_for_player(events, player_name)
                    print(f"  ✓ Telemetry parsed ({len(events)} events)")

            all_matches.append({
                **parsed_match,
                'player_stats': my_participant,
                'team_info':    team_info,
                'telemetry':    telemetry_info,
                'total_teams':  len(rosters),
            })

        return all_matches

    # ─────────────────────────────────────────────
    #  OUTPUT
    # ─────────────────────────────────────────────

    def print_matches(self, matches):
        if not matches:
            print("No matches to display")
            return

        for i, match in enumerate(matches, 1):
            print(f"\n{'='*80}")
            print(f"  MATCH #{i}  —  {match['created_at']}")
            print(f"{'='*80}")
            print(f"  ID          : {match['match_id']}")
            print(f"  Mode        : {match['game_mode']}  |  Type: {match['match_type']}")
            print(f"  Map         : {match['map_name']}")
            print(f"  Duration    : {match['duration_minutes']} min")
            print(f"  Patch       : {match.get('patch_version', 'N/A')}")
            print(f"  Total teams : {match.get('total_teams', 'N/A')}")

            # ── Player stats ──────────────────────────────────────────
            s = match.get('player_stats')
            if s:
                print(f"\n  ── Player Stats ──────────────────────────────────────")
                print(f"  Player        : {s['player_name']}")
                print(f"  Rank          : #{s['rank']}  (kill rank: #{s['kill_place']})")
                print(f"  Death type    : {s['death_type']}")
                print()
                print(f"  Kills         : {s['kills']}")
                print(f"  Headshot kills: {s['headshot_kills']}")
                print(f"  Road kills    : {s['road_kills']}")
                print(f"  Team kills    : {s['team_kills']}")
                print(f"  Kill streaks  : {s['kill_streaks']}")
                print(f"  Longest kill  : {s['longest_kill_m']} m")
                print(f"  Damage dealt  : {s['damage_dealt']}")
                print(f"  Assists       : {s['assists']}")
                print(f"  DBNOs         : {s['dbnos']}")
                print(f"  Revives       : {s['revives']}")
                print()
                print(f"  Survival time : {s['survival_time_min']} min")
                print(f"  Walk dist     : {s['walk_distance_km']} km")
                print(f"  Ride dist     : {s['ride_distance_km']} km")
                print(f"  Swim dist     : {s['swim_distance_km']} km")
                print(f"  Total dist    : {s['walk_distance_km']+s['ride_distance_km']+s['swim_distance_km']:.2f} km")
                print()
                print(f"  Heals used    : {s['heals_used']}")
                print(f"  Boosts used   : {s['boosts_used']}")
                print(f"  Weapons acq.  : {s['weapons_acquired']}")
                print(f"  Vehicle destr.: {s['vehicle_destroys']}")

            # ── Team info ─────────────────────────────────────────────
            t = match.get('team_info')
            if t:
                won_str = "🏆 WIN" if t['team_won'] else f"#{t['team_rank']}"
                print(f"\n  ── Team Info ─────────────────────────────────────────")
                print(f"  Team result   : {won_str}")
                if t['teammates']:
                    print(f"  Teammates:")
                    for tm in t['teammates']:
                        print(f"    • {tm['name']:20s}  kills={tm['kills']}  dmg={tm['damage']}")

            # ── Telemetry ─────────────────────────────────────────────
            tel = match.get('telemetry')
            if tel:
                print(f"\n  ── Telemetry Highlights ──────────────────────────────")
                print(f"  Damage taken events: {tel['damage_taken_events']}")

                if tel['kills']:
                    print(f"\n  Kills ({len(tel['kills'])}):")
                    for k in tel['kills']:
                        hs = " [HEADSHOT]" if k['headshot'] else ""
                        print(f"    ✦ {k['victim']:20s}  weapon={k['weapon']:30s}  dist={k['distance_m']}m{hs}")

                lk = tel.get('longest_kill')
                if lk:
                    print(f"\n  🎯 Longest Kill:")
                    print(f"     Victim  : {lk['victim']}")
                    print(f"     Weapon  : {lk['weapon']}")
                    print(f"     Distance: {lk['distance_m']} m")
                    print(f"     Headshot: {lk['headshot']}")

                if tel['weapons_picked_up']:
                    seen = []
                    unique = []
                    for w in tel['weapons_picked_up']:
                        if w['item_id'] not in seen:
                            seen.append(w['item_id'])
                            unique.append(w['item_id'])
                    print(f"\n  Weapons picked up ({len(unique)} unique):")
                    for wid in unique:
                        print(f"    • {wid}")

                if tel.get('death'):
                    d = tel['death']
                    print(f"\n  ☠ Death:")
                    print(f"     Killed by : {d['killed_by']}")
                    print(f"     Weapon    : {d['weapon']}")

    def save_to_json(self, matches, filename='pubg_matches_enhanced.json'):
        with open(filename, 'w', encoding='utf-8') as f:
            json.dump(matches, f, indent=2, ensure_ascii=False)
        print(f"\nSaved to {filename}")


# ─────────────────────────────────────────────────────────────────────────────
#  MAIN
# ─────────────────────────────────────────────────────────────────────────────

def main():
    API_KEY     = "eyJ0eXAiOiJKV1QiLCJhbGciOiJIUzI1NiJ9.eyJqdGkiOiIyMThmZDc4MC1jOGFhLTAxM2QtMWI2Ni0wNjFhOWQ1YjYxYWYiLCJpc3MiOiJnYW1lbG9ja2VyIiwiaWF0IjoxNzM5MDYwNjYxLCJwdWIiOiJibHVlaG9sZSIsInRpdGxlIjoicHViZyIsImFwcCI6Ii0xODA1OTMzNy0wYTQ0LTQzZjYtYWE0OS01NTM4YmZhZjEzOTUifQ.p2ZG2vQW9Nrp73Iul77UmCLwKKlcsXLz2xSoO2EhsGA"
    PLATFORM    = "steam"
    PLAYER_NAME = "F-1-R-E"
    NUM_MATCHES = 3             # increase as needed (each match = 1 API call + 1 telemetry call)
    FETCH_TELEMETRY = True      # set False to skip telemetry (faster, but no weapon data)

    fetcher = PUBGMatchesFetcher(API_KEY, PLATFORM)
    matches = fetcher.get_last_matches(PLAYER_NAME, NUM_MATCHES, FETCH_TELEMETRY)

    if matches:
        fetcher.print_matches(matches)
        fetcher.save_to_json(matches)
        print(f"\nDone — {len(matches)} match(es) fetched.")
    else:
        print("Failed to fetch matches.")


if __name__ == "__main__":
    main()