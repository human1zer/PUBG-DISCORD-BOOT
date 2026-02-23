import json
import os
import logging
from typing import List, Tuple, Optional

from bot import IntegratedPUBGBot

# Setup logging
logging.basicConfig(
    level=logging.INFO,
    format='[%(asctime)s] [%(levelname)-8s] %(name)s: %(message)s',
    datefmt='%Y-%m-%d %H:%M:%S'
)
logger = logging.getLogger(__name__)


def load_players_from_file(filename: str = "players.txt") -> List[Tuple[str, str]]:
    """Load player names from file — name only, platform always defaults to steam"""
    if not os.path.exists(filename):
        logger.warning(f"⚠️  '{filename}' not found. Creating example file...")
        with open(filename, 'w', encoding='utf-8') as f:
            f.write("# PUBG Players to Track\n")
            f.write("# Format: PlayerName  (one per line, no platform needed)\n")
            f.write("#\n")
            f.write("# Examples:\n")
            f.write("# PlayerName1\n")
            f.write("# PlayerName2\n")
        logger.info(f"✅ Created '{filename}'. Add player names and run again.")
        return []
    
    players = []
    with open(filename, 'r', encoding='utf-8') as f:
        for line in f:
            line = line.strip()
            if not line or line.startswith('#'):
                continue
            
            # Support legacy format (name,platform) but ignore the platform value
            if ',' in line:
                name = line.split(',', 1)[0].strip()
            else:
                name = line
            
            if name:
                players.append((name, 'steam'))
    
    return players


def load_config(filename: str = "config.json") -> Optional[dict]:
    if not os.path.exists(filename):
        logger.warning(f"⚠️  '{filename}' not found. Creating default config...")
        default_config = {
            "pubg_api_key": "YOUR_PUBG_API_KEY_HERE",
            "discord_token": "YOUR_DISCORD_BOT_TOKEN_HERE",
            "discord_channel_id": 123456789012345678,
            "check_interval_seconds": 150,
            "request_delay": 7.0,
            "max_retries": 3
        }
        with open(filename, 'w', encoding='utf-8') as f:
            json.dump(default_config, f, indent=2)
        logger.info(f"✅ Created '{filename}'")
        print("\n📝 Setup Instructions:")
        print("\n=== PUBG API Setup ===")
        print("1. Get your API key from: https://developer.pubg.com/")
        print("2. Add it to config.json as 'pubg_api_key'")
        print("\n=== Discord Bot Setup ===")
        print("3. Go to https://discord.com/developers/applications")
        print("4. Create a New Application")
        print("5. Go to 'Bot' section and create a bot")
        print("6. Copy the bot token and add to config.json as 'discord_token'")
        print("7. Enable 'MESSAGE CONTENT INTENT' in Bot settings")
        print("8. Go to OAuth2 > URL Generator")
        print("9. Select 'bot' scope and 'Send Messages' permission")
        print("10. Copy the URL and invite the bot to your server")
        print("11. Get your channel ID (Right click channel > Copy ID)")
        print("    (Enable Developer Mode in Discord settings if needed)")
        print("12. Add channel ID to config.json as 'discord_channel_id'")
        return None
    
    with open(filename, 'r', encoding='utf-8') as f:
        return json.load(f)


def main():
    print("="*80)
    print("PUBG INTEGRATED TRACKER & DISCORD BOT v2.2")
    print("="*80)
    print("Features:")
    print("  ✅ Fully async architecture (no blocking)")
    print("  ✅ Enhanced Discord embeds with detailed stats")
    print("  ✅ Continuous match tracking")
    print("  ✅ Auto-post to Discord")
    print("  ✅ No double-posting (even with multiple players in same match)")
    print("  ✅ Persistent history (survives restarts)")
    print("  ✅ Weekly statistics and leaderboards")
    print("  ✅ Dynamic player management (!addplayer, !removeplayer, !listplayers)")
    print("  ✅ Fixed match categorization:")
    print("      - airoyale = CASUAL")
    print("      - official = NORMAL")
    print("="*80)
    print()
    
    config = load_config()
    if not config:
        return
    
    pubg_api_key = config.get('pubg_api_key')
    discord_token = config.get('discord_token')
    channel_id = config.get('discord_channel_id')
    check_interval = config.get('check_interval_seconds', 300)
    request_delay = config.get('request_delay', 7.0)
    max_retries = config.get('max_retries', 3)
    weekly_channel_id = config.get('weekly_channel_id', channel_id)
    
    if pubg_api_key == "YOUR_PUBG_API_KEY_HERE" or not pubg_api_key:
        logger.error("❌ Please add your PUBG API key to 'config.json'")
        logger.info("   Get your API key from: https://developer.pubg.com/")
        return
    
    if discord_token == "YOUR_DISCORD_BOT_TOKEN_HERE" or not discord_token:
        logger.error("❌ Please add your Discord bot token to 'config.json'")
        return
    
    if channel_id == 123456789012345678:
        logger.error("❌ Please add your Discord channel ID to 'config.json'")
        return
    
    players = load_players_from_file()
    if not players:
        logger.warning("\n⚠️  No players found. Add player names to 'players.txt' and run again.")
        logger.warning("   Or use !addplayer <name> in Discord after bot starts.")
    
    logger.info(f"📋 Players to track: {len(players)}")
    for idx, (name, _) in enumerate(players, 1):
        logger.info(f"   {idx}. {name}")
    
    logger.info(f"\n⏱️  Settings:")
    logger.info(f"   Check interval: {check_interval}s ({check_interval/60:.1f} minutes)")
    logger.info(f"   Request delay: {request_delay}s")
    logger.info(f"   Discord channel: {channel_id}")
    logger.info(f"\n🚀 Starting integrated bot...")
    logger.info(f"   Press Ctrl+C to stop\n")
    
    bot = IntegratedPUBGBot(
        discord_token=discord_token,
        channel_id=channel_id,
        api_key=pubg_api_key,
        players=players,
        check_interval=check_interval,
        request_delay=request_delay,
        max_retries=max_retries,
        weekly_channel_id=weekly_channel_id
    )
    
    try:
        bot.run()
    except KeyboardInterrupt:
        print("\n\n" + "="*80)
        print("⛔ STOPPED BY USER")
        print("="*80)
        print(f"Total cycles completed: {bot.cycle_number - 1}")
        print(f"Posted matches saved in: posted_matches.json")
        print("\n✅ Bot stopped successfully!")


if __name__ == "__main__":
    main()