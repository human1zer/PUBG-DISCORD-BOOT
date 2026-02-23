import json

with open(r"\\10.0.0.9\DISCORD-BOOT\discord_pro\match_history.json", "r", encoding="utf-8") as f:
    data = json.load(f)


# إذا dict → خذ القيم
if isinstance(data, dict):
    entries = data.values()
else:
    entries = data

valid = []

for entry in entries:

    # تجاهل أي شي مو dict
    if not isinstance(entry, dict):
        continue

    stats = entry.get("stats")

    # أحياناً stats نفسها مو dict
    if not isinstance(stats, dict):
        continue

    lk = stats.get("longest_kill")

    if isinstance(lk, (int, float)):
        valid.append((lk, entry))

top10 = sorted(valid, key=lambda x: x[0], reverse=True)[:10]

for i, (lk, entry) in enumerate(top10, 1):
    print(f"{i}. {lk}m - {entry.get('player_name')} - {entry.get('match_id')}")
