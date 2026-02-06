import discord
from discord.ext import tasks, commands
import aiohttp
import json
import os
import asyncio
import traceback
from datetime import datetime, timezone, timedelta
from typing import List, Tuple, Dict, Optional, Set
import logging

# Import the weekly stats module
from weekly_stats import WeeklyStatsManager

# Setup logging
logging.basicConfig(
    level=logging.INFO,
    format='[%(asctime)s] [%(levelname)-8s] %(name)s: %(message)s',
    datefmt='%Y-%m-%d %H:%M:%S'
)
logger = logging.getLogger(__name__)


class AsyncPUBGMatchTracker:
    """Async PUBG API tracker with rate limiting and retry logic"""
    
    def __init__(self, api_key: str, request_delay: float = 7.0, max_retries: int = 3):
        """
        Initialize async tracker with rate limit compliance
        
        Args:
            api_key: PUBG API key
            request_delay: Delay between API requests in seconds (default 7s)
            max_retries: Maximum retry attempts for failed requests
        """
        self.api_key = api_key
        self.base_url = "https://api.pubg.com/shards"
        self.headers = {
            "Authorization": f"Bearer {api_key}",
            "Accept": "application/vnd.api+json"
        }
        self.request_delay = request_delay
        self.max_retries = max_retries
        
        # Tracking data
        self.results = []
        self.request_count = 0
        self.cycle_start_time = None
        self.last_match_ids: Dict[str, str] = {}
        self.processed_matches_this_cycle: Set[str] = set()
        
        # Session management
        self.session: Optional[aiohttp.ClientSession] = None
    
    async def ensure_session(self):
        """Ensure aiohttp session exists"""
        if self.session is None or self.session.closed:
            timeout = aiohttp.ClientTimeout(total=30)
            self.session = aiohttp.ClientSession(timeout=timeout)
    
    async def close_session(self):
        """Close aiohttp session"""
        if self.session and not self.session.closed:
            await self.session.close()
    
    def reset_cycle(self):
        """Reset tracker for new cycle"""
        self.results = []
        self.request_count = 0
        self.cycle_start_time = datetime.now()
        self.processed_matches_this_cycle = set()
        logger.info("🔄 Tracker cycle reset")
    
    def check_rate_limit(self, headers: dict):
        """Check and log rate limit headers"""
        limit = headers.get('X-RateLimit-Limit', 'N/A')
        remaining = headers.get('X-RateLimit-Remaining', 'N/A')
        
        if remaining != 'N/A':
            logger.info(f"📊 Rate Limit: {remaining}/{limit} remaining")
            if int(remaining) < 3:
                logger.warning(f"⚠️  WARNING: Only {remaining} requests left!")
    
    async def make_request_with_retry(self, url: str, context: str = "request") -> Optional[dict]:
        """Make async HTTP request with exponential backoff retry"""
        await self.ensure_session()
        
        for attempt in range(self.max_retries):
            try:
                self.request_count += 1
                
                async with self.session.get(url, headers=self.headers) as response:
                    # Check rate limit status
                    self.check_rate_limit(response.headers)
                    
                    # Handle rate limiting
                    if response.status == 429:
                        reset_time = response.headers.get('X-RateLimit-Reset')
                        if reset_time:
                            wait_time = max(int(reset_time) - int(datetime.now().timestamp()) + 2, 60)
                            logger.warning(f"⚠️  Rate limited! Waiting {wait_time}s until reset...")
                        else:
                            wait_time = 60
                            logger.warning(f"⚠️  Rate limited! Waiting {wait_time}s...")
                        
                        await asyncio.sleep(wait_time)
                        continue
                    
                    # Raise for other HTTP errors
                    response.raise_for_status()
                    
                    # Parse and return JSON
                    return await response.json()
                    
            except aiohttp.ClientError as e:
                if attempt == self.max_retries - 1:
                    logger.error(f"❌ Failed {context} after {self.max_retries} attempts: {e}")
                    return None
                    
                wait_time = (attempt + 1) * 5
                logger.warning(f"⚠️  Error on {context}, retrying in {wait_time}s... ({attempt + 1}/{self.max_retries})")
                await asyncio.sleep(wait_time)
            
            except Exception as e:
                logger.error(f"❌ Unexpected error on {context}: {e}")
                return None
        
        return None
    
    async def get_latest_match(
        self, 
        player_name: str, 
        platform: str = "steam", 
        all_tracked_players: Optional[List[str]] = None
    ) -> Optional[dict]:
        """Fetch only the most recent match for a player"""
        player_url = f"{self.base_url}/{platform}/players?filter[playerNames]={player_name}"
        
        try:
            data = await self.make_request_with_retry(player_url, f"player '{player_name}'")
            
            if not data or not data.get('data'):
                logger.warning(f"❌ Player '{player_name}' not found on platform '{platform}'!")
                return None
            
            player = data['data'][0]
            match_ids = [match['id'] for match in player['relationships']['matches']['data']]
            
            if not match_ids:
                logger.warning(f"❌ No matches found for '{player_name}'")
                return None
            
            latest_match_id = match_ids[0]
            
            # Check if this match was already processed THIS CYCLE
            if latest_match_id in self.processed_matches_this_cycle:
                logger.info(f"✅ Found player: {player['attributes']['name']}")
                logger.info(f"   ⚠️  MATCH ALREADY PROCESSED THIS CYCLE (another tracked player in same game)")
                logger.info(f"   Match ID: {latest_match_id[:16]}...")
                self.last_match_ids[player_name] = latest_match_id
                return None
            
            # Check if this is the same match as last cycle
            if player_name in self.last_match_ids:
                if self.last_match_ids[player_name] == latest_match_id:
                    logger.info(f"✅ Found player: {player['attributes']['name']}")
                    logger.info(f"   ⚠️  SAME MATCH as last cycle - SKIPPING!")
                    logger.info(f"   Match ID: {latest_match_id[:16]}...")
                    return None
            
            logger.info(f"✅ Found player: {player['attributes']['name']}")
            logger.info(f"   🆕 NEW MATCH FOUND!")
            logger.info(f"   Match ID: {latest_match_id[:16]}...")
            
            # Mark this match as processed in this cycle
            self.processed_matches_this_cycle.add(latest_match_id)
            
            # Update last match ID for this player
            self.last_match_ids[player_name] = latest_match_id
            
            # Add delay before match details request
            await asyncio.sleep(self.request_delay)
            
            # Get match data with ALL tracked players in it
            match_data = await self.get_match_details(
                latest_match_id, 
                platform, 
                all_tracked_players or [player_name]
            )
            
            if match_data:
                self.results.append(match_data)
                logger.info(f"   ✅ Match data saved! (Total: {len(self.results)})")
                return match_data
            
            return None
                
        except Exception as e:
            logger.error(f"❌ Error fetching player '{player_name}': {e}")
            traceback.print_exc()
            return None
    
    async def get_match_details(
        self, 
        match_id: str, 
        platform: str, 
        tracked_players: List[str]
    ) -> Optional[dict]:
        """Fetch detailed information about a specific match"""
        match_url = f"{self.base_url}/{platform}/matches/{match_id}"
        
        try:
            data = await self.make_request_with_retry(match_url, f"match {match_id[:8]}")
            
            if not data:
                return None
            
            match_attrs = data['data']['attributes']
            
            # Extract match information
            game_mode = match_attrs.get('gameMode', 'Unknown')
            match_type = match_attrs.get('matchType', 'Unknown')
            is_custom = match_attrs.get('isCustomMatch', False)
            map_name = match_attrs.get('mapName', 'Unknown')
            duration = match_attrs.get('duration', 0)
            created_at = match_attrs.get('createdAt', '')
            
            match_category = self.determine_match_category(game_mode, match_type, is_custom)
            
            included = data.get('included', [])
            
            # Find stats for ALL tracked players in this match
            all_players_stats = {}
            
            for player_name in tracked_players:
                stats = self.find_player_stats(included, player_name)
                if stats:
                    all_players_stats[player_name] = stats
                    logger.info(f"   👤 Found stats for: {player_name}")
            
            match_data = {
                "match_id": match_id,
                "match_category": match_category,
                "game_mode": game_mode,
                "match_type": match_type,
                "is_custom": is_custom,
                "map": map_name,
                "duration_seconds": duration,
                "duration_minutes": duration // 60,
                "played_at": created_at,
                "played_at_formatted": self.format_datetime(created_at),
                "all_players_stats": all_players_stats
            }
            
            return match_data
            
        except Exception as e:
            logger.error(f"❌ Error fetching match {match_id}: {e}")
            traceback.print_exc()
            return None
    
    def determine_match_category(self, game_mode: str, match_type: str, is_custom: bool) -> str:
        """Determine match category from game mode and type"""
        if is_custom:
            return "CUSTOM"
        
        game_mode_lower = game_mode.lower()
        match_type_lower = match_type.lower()
        
        if 'competitive' in match_type_lower or 'ranked' in match_type_lower:
            return "RANKED"
        
        arcade_keywords = ['war', 'zombie', 'training', 'tdm', 'conquest', 'intense', 
                          'esports', 'event', 'lab', 'arcade', 'casual']
        if any(keyword in game_mode_lower for keyword in arcade_keywords):
            return "ARCADE"
        
        normal_modes = ['solo', 'solo-fpp', 'duo', 'duo-fpp', 'squad', 'squad-fpp']
        
        if game_mode_lower in normal_modes:
            if match_type_lower in ['official', 'seasonal']:
                return "NORMAL"
            return f"NORMAL ({match_type})"
        
        return f"UNKNOWN ({game_mode})"
    
    def find_player_stats(self, included: list, player_name: str) -> Optional[dict]:
        """Find the specific player's statistics from match data"""
        for item in included:
            if item['type'] == 'participant':
                stats = item['attributes']['stats']
                if stats.get('name', '').lower() == player_name.lower():
                    survival_seconds = stats.get('timeSurvived', 0)
                    survival_minutes = round(survival_seconds / 60, 2)
                    
                    return {
                        "rank": stats.get('winPlace', 'N/A'),
                        "kills": stats.get('kills', 0),
                        "damage_dealt": round(stats.get('damageDealt', 0), 2),
                        "assists": stats.get('assists', 0),
                        "dbnos": stats.get('DBNOs', 0),
                        "headshot_kills": stats.get('headshotKills', 0),
                        "longest_kill": round(stats.get('longestKill', 0), 2),
                        "revives": stats.get('revives', 0),
                        "team_kills": stats.get('teamKills', 0),
                        "vehicle_destroys": stats.get('vehicleDestroys', 0),
                        "weapons_acquired": stats.get('weaponsAcquired', 0),
                        "boosts_used": stats.get('boosts', 0),
                        "heals_used": stats.get('heals', 0),
                        "walk_distance": round(stats.get('walkDistance', 0), 2),
                        "ride_distance": round(stats.get('rideDistance', 0), 2),
                        "swim_distance": round(stats.get('swimDistance', 0), 2),
                        "survival_time_minutes": survival_minutes,
                        "death_type": stats.get('deathType', 'N/A'),
                        "kill_streaks": stats.get('killStreaks', 0),
                        "road_kills": stats.get('roadKills', 0)
                    }
        return None
    
    def format_datetime(self, datetime_str: str) -> str:
        """Format ISO datetime to readable format"""
        try:
            dt = datetime.fromisoformat(datetime_str.replace('Z', '+00:00'))
            return dt.strftime('%Y-%m-%d %H:%M:%S UTC')
        except:
            return datetime_str
    
    def print_cycle_summary(self, cycle_number: int):
        """Print summary of current cycle"""
        if self.cycle_start_time:
            elapsed = (datetime.now() - self.cycle_start_time).total_seconds()
        else:
            elapsed = 0
        
        logger.info(f"\n{'='*80}")
        logger.info(f"CYCLE #{cycle_number} SUMMARY")
        logger.info(f"{'='*80}")
        logger.info(f"New Matches: {len(self.results)}")
        logger.info(f"API Requests: {self.request_count}")
        logger.info(f"Cycle Time: {int(elapsed)}s ({elapsed/60:.1f} minutes)")
        logger.info(f"{'='*80}")
        
        if self.results:
            logger.info("\n🆕 NEW Matches Found:")
            for idx, match in enumerate(self.results, 1):
                all_stats = match.get('all_players_stats', {})
                players_list = ', '.join(all_stats.keys())
                total_kills = sum(s.get('kills', 0) for s in all_stats.values())
                best_rank = min(s.get('rank', 99) for s in all_stats.values()) if all_stats else 'N/A'
                logger.info(f"  {idx}. Players: {players_list}")
                logger.info(f"      Best Rank: #{best_rank} | Total Kills: {total_kills}")
        else:
            logger.info("\n⚠️  No new matches found this cycle")


class IntegratedPUBGBot:
    """Enhanced PUBG Discord Bot with async architecture"""
    
    def __init__(
        self, 
        discord_token: str,
        channel_id: int,
        api_key: str,
        players: List[Tuple[str, str]],
        check_interval: int = 300,
        request_delay: float = 7.0,
        max_retries: int = 3
    ):
        """
        Initialize integrated bot
        
        Args:
            discord_token: Discord bot token
            channel_id: Discord channel ID to post to
            api_key: PUBG API key
            players: List of (player_name, platform) tuples
            check_interval: Seconds between match checks (default 300 = 5 minutes)
            request_delay: Delay between API requests (default 7s)
            max_retries: Max retries for failed requests (default 3)
        """
        self.discord_token = discord_token
        self.channel_id = channel_id
        self.players = players
        self.check_interval = check_interval
        
        # Initialize PUBG tracker
        self.tracker = AsyncPUBGMatchTracker(api_key, request_delay, max_retries)
        self.stats_manager = WeeklyStatsManager(max_history=500)
        
        # Track posted matches to prevent double-posting
        self.posted_matches = self.load_posted_matches()
        
        # Setup Discord client
        intents = discord.Intents.default()
        intents.message_content = True
        self.client = discord.Client(intents=intents)
        
        # Register events
        self.client.event(self.on_ready)
        
        self.cycle_number = 1
        self.is_running = False
    
    def load_posted_matches(self, filename: str = "posted_matches.json") -> Set[str]:
        """Load history of posted matches from file"""
        if os.path.exists(filename):
            try:
                with open(filename, 'r', encoding='utf-8') as f:
                    data = json.load(f)
                    logger.info(f"📋 Loaded {len(data)} previously posted matches")
                    return set(data)
            except Exception as e:
                logger.error(f"⚠️  Error loading posted matches: {e}")
                return set()
        return set()
    
    def save_posted_matches(self, filename: str = "posted_matches.json", max_history: int = 100):
        """Save history of posted matches to file (keep only recent matches)"""
        try:
            # Convert set to list and keep only the most recent entries
            matches_list = list(self.posted_matches)[-max_history:]
            self.posted_matches = set(matches_list)
            with open(filename, 'w', encoding='utf-8') as f:
                json.dump(matches_list, f, indent=2)
            logger.info(f"💾 Saved {len(matches_list)} match IDs (max: {max_history})")
        except Exception as e:
            logger.error(f"⚠️  Error saving posted matches: {e}")
    
    async def on_ready(self):
        """Called when bot connects to Discord"""
        logger.info(f'✅ Bot connected as {self.client.user}')
        logger.info(f'📡 Tracking {len(self.players)} players')
        logger.info(f'📢 Posting to channel ID: {self.channel_id}')
        logger.info(f'🔄 Checking for new matches every {self.check_interval} seconds...\n')
        
        # Start the background tasks
        if not self.is_running:
            self.check_matches_loop.start()
            self.weekly_summary_loop.start()
            self.is_running = True
    
    @tasks.loop(seconds=1)
    async def check_matches_loop(self):
        """Main async loop to check for new matches"""
        try:
            logger.info(f"\n{'#'*80}")
            logger.info(f"# CYCLE {self.cycle_number} - {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
            logger.info(f"{'#'*80}\n")
            
            self.tracker.reset_cycle()
            
            # Create list of all tracked player names
            tracked_player_names = [name for name, _ in self.players]
            
            # Fetch latest matches for all players
            for idx, (player_name, platform) in enumerate(self.players, 1):
                logger.info(f"{'─'*80}")
                logger.info(f"[{idx}/{len(self.players)}] Fetching: {player_name} (Platform: {platform})")
                logger.info(f"{'─'*80}")
                
                await self.tracker.get_latest_match(player_name, platform, tracked_player_names)
                
                if idx < len(self.players):
                    logger.info(f"⏳ Waiting {self.tracker.request_delay}s before next player...")
                    await asyncio.sleep(self.tracker.request_delay)
                logger.info("")
            
            # Print summary
            self.tracker.print_cycle_summary(self.cycle_number)
            
            # Post new matches to Discord
            if self.tracker.results:
                await self.post_matches_to_discord(self.tracker.results)
            
            self.cycle_number += 1
            
            logger.info(f"\n{'='*80}")
            logger.info(f"✅ Cycle {self.cycle_number - 1} complete! Next check in {self.check_interval}s...")
            logger.info(f"{'='*80}\n")
            
            # Wait for next cycle
            await asyncio.sleep(self.check_interval)
            
        except Exception as e:
            logger.error(f"❌ Error in check loop: {e}")
            traceback.print_exc()
            # Wait before retrying
            await asyncio.sleep(60)
    
    @tasks.loop(hours=1)
    async def weekly_summary_loop(self):
        """Post weekly summary every Wednesday at 16:00 UTC"""
        try:
            now = datetime.now(timezone.utc)
            
            # Only post on Wednesdays (2 = Wednesday) at 16:00 UTC
            if now.weekday() != 2 or now.hour != 16:
                return
            
            logger.info("\n" + "="*80)
            logger.info("📊 GENERATING WEEKLY SUMMARY - Wednesday 16:00 UTC")
            logger.info("="*80)
            
            weekly_data = self.stats_manager.calculate_weekly_best(days=7)
            
            if not weekly_data:
                logger.warning("⚠️ No data available for weekly summary")
                return
            
            channel = self.client.get_channel(self.channel_id)
            if not channel:
                logger.error(f"❌ Channel not found: {self.channel_id}")
                return
            
            # Post best player embed
            best_embed = self.stats_manager.create_weekly_embed(weekly_data)
            await channel.send(embed=best_embed)
            logger.info("✅ Best player summary posted!")
            
            # Post leaderboard
            await asyncio.sleep(2)
            leaderboard_embed = self.stats_manager.create_leaderboard_embed(weekly_data, top_n=5)
            await channel.send(embed=leaderboard_embed)
            logger.info("✅ Leaderboard posted!")
            
            logger.info("="*80 + "\n")
            
        except Exception as e:
            logger.error(f"❌ Error posting weekly summary: {e}")
            traceback.print_exc()
    
    async def post_matches_to_discord(self, matches: List[dict]):
        """Post new matches to Discord with enhanced embeds"""
        try:
            channel = self.client.get_channel(self.channel_id)
            if not channel:
                logger.error(f"❌ Channel not found: {self.channel_id}")
                return
            
            new_matches = []
            
            # Filter out already posted matches
            for match in matches:
                match_id = match['match_id']
                if match_id not in self.posted_matches:
                    new_matches.append(match)
                    self.posted_matches.add(match_id)
                else:
                    logger.info(f"⏭️  Skipping already posted match: {match_id[:16]}...")
            
            if not new_matches:
                logger.info(f"📭 No new matches to post (all already posted)")
                return
            
            # Save updated posted matches list
            self.save_posted_matches()
            
            logger.info(f"\n📤 Posting {len(new_matches)} new matches to Discord...")
            
            # Post each match as an embed
            for idx, match in enumerate(new_matches, 1):
                embed = self.create_enhanced_match_embed(match, idx, len(new_matches))
                if embed:
                    await channel.send(embed=embed)
                    players_in_match = list(match.get('all_players_stats', {}).keys())
                    logger.info(f"   ✅ Posted match {idx}/{len(new_matches)}: {', '.join(players_in_match)}")
                else:
                    logger.warning(f"   ⚠️  Skipped match {idx}/{len(new_matches)}: No player data")
                
                # Small delay between messages
                if idx < len(new_matches):
                    await asyncio.sleep(2)
            
            logger.info(f"   🎉 All {len(new_matches)} matches posted!")
            
            # Save match history for weekly stats
            self.save_matches_for_stats(new_matches)
            
        except Exception as e:
            logger.error(f"❌ Error posting to Discord: {e}")
            traceback.print_exc()
    
    def save_matches_for_stats(self, matches: List[dict]):
        """Convert multi-player matches to individual player records for stats tracking"""
        try:
            individual_matches = []
            
            for match in matches:
                all_players_stats = match.get('all_players_stats', {})
                
                # Create a separate match record for each player
                for player_name, player_stats in all_players_stats.items():
                    individual_match = {
                        'player_name': player_name,
                        'match_id': match['match_id'],
                        'match_category': match['match_category'],
                        'game_mode': match['game_mode'],
                        'match_type': match['match_type'],
                        'is_custom': match['is_custom'],
                        'map': match['map'],
                        'duration_seconds': match['duration_seconds'],
                        'duration_minutes': match['duration_minutes'],
                        'played_at': match['played_at'],
                        'played_at_formatted': match['played_at_formatted'],
                        'player_stats': player_stats
                    }
                    individual_matches.append(individual_match)
            
            if individual_matches:
                self.stats_manager.save_match_history(individual_matches)
                logger.info(f"📊 Saved {len(individual_matches)} player records for weekly stats")
                
        except Exception as e:
            logger.error(f"⚠️ Error saving match history: {e}")
            traceback.print_exc()
    
    def create_enhanced_match_embed(self, match: dict, match_num: int, total_matches: int) -> Optional[discord.Embed]:
        """Create an enhanced Discord embed with better formatting and more details"""
        all_players_stats = match.get('all_players_stats', {})
        
        if not all_players_stats:
            return None
        
        # Determine embed color based on best rank
        ranks = [stats.get('rank', 99) for stats in all_players_stats.values()]
        best_rank = min(ranks)
        
        if best_rank == 1:
            color = discord.Color.gold()
            rank_emoji = "🥇"
        elif best_rank <= 3:
            color = discord.Color.from_rgb(192, 192, 192)  # Silver
            rank_emoji = "🥈"
        elif best_rank <= 5:
            color = discord.Color.from_rgb(205, 127, 50)  # Bronze
            rank_emoji = "🥉"
        elif best_rank <= 10:
            color = discord.Color.blue()
            rank_emoji = "🏅"
        else:
            color = discord.Color.red()
            rank_emoji = "💀"
        
        # Get map emoji
        map_emojis = {
            'Baltic_Main': '🏔️',
            'Desert_Main': '🏜️',
            'DihorOtok_Main': '🏝️',
            'Erangel_Main': '🌾',
            'Heaven_Main': '🌸',
            'Kiki_Main': '🌴',
            'Range_Main': '🎯',
            'Savage_Main': '🌴',
            'Summerland_Main': '☀️',
            'Tiger_Main': '🐯',
            'Chimera_Main': '🦁',
        }
        map_name = match.get('map', 'Unknown')
        map_emoji = map_emojis.get(map_name, '🗺️')
        
        # Create title
        player_count = len(all_players_stats)
        category = match.get('match_category', 'MATCH')
        title = f"{rank_emoji} {category} - {player_count} Player{'s' if player_count > 1 else ''}"
        
        # Create description with match info
        mode_display = match.get('game_mode', 'Unknown').replace('-fpp', ' (FPP)').title()
        description = (
            f"{map_emoji} **{map_name.replace('_Main', '')}** • "
            f"🎮 **{mode_display}**\n"
            f"⏱️ Duration: **{match.get('duration_minutes', 0)}** min • "
            f"🕐 {self.format_time_ago(match.get('played_at', ''))}"
        )
        
        embed = discord.Embed(
            title=title,
            description=description,
            color=color,
            timestamp=datetime.now()
        )
        
        # Add team performance summary
        total_kills = sum(stats.get('kills', 0) for stats in all_players_stats.values())
        total_damage = sum(stats.get('damage_dealt', 0) for stats in all_players_stats.values())
        total_headshots = sum(stats.get('headshot_kills', 0) for stats in all_players_stats.values())
        avg_survival = sum(stats.get('survival_time_minutes', 0) for stats in all_players_stats.values()) / len(all_players_stats)
        
        # Calculate headshot percentage
        hs_percent = (total_headshots / total_kills * 100) if total_kills > 0 else 0
        
        embed.add_field(
            name="📊 Team Performance",
            value=(
                f"🎯 **Rank:** #{best_rank}\n"
                f"💀 **Kills:** {total_kills} ({total_headshots}🎯 {hs_percent:.0f}%)\n"
                f"💥 **Damage:** {total_damage:,.0f}\n"
                f"⏳ **Avg Survival:** {avg_survival:.1f} min"
            ),
            inline=False
        )
        
        # Add individual player stats - sorted by performance
        sorted_players = sorted(
            all_players_stats.items(),
            key=lambda x: (x[1].get('rank', 99), -x[1].get('kills', 0), -x[1].get('damage_dealt', 0))
        )
        
        for player_name, stats in sorted_players:
            # Performance metrics
            rank = stats.get('rank', 'N/A')
            kills = stats.get('kills', 0)
            damage = stats.get('damage_dealt', 0)
            survival = stats.get('survival_time_minutes', 0)
            
            # Combat details
            assists = stats.get('assists', 0)
            dbnos = stats.get('dbnos', 0)
            headshots = stats.get('headshot_kills', 0)
            longest_kill = stats.get('longest_kill', 0)
            
            # Movement
            walk_dist = stats.get('walk_distance', 0) / 1000
            ride_dist = stats.get('ride_distance', 0) / 1000
            total_dist = walk_dist + ride_dist
            
            # Items
            heals = stats.get('heals_used', 0)
            boosts = stats.get('boosts_used', 0)
            
            # Rank emoji
            if rank == 1:
                player_rank_emoji = "🥇"
            elif rank <= 3:
                player_rank_emoji = "🥈"
            elif rank <= 5:
                player_rank_emoji = "🥉"
            elif rank <= 10:
                player_rank_emoji = "🏅"
            else:
                player_rank_emoji = "💀"
            
            # Calculate K/D ratio (dbnos as proxy for deaths if not winner)
            kd_display = f"{kills}/{dbnos}" if rank != 1 else f"{kills}/0"
            
            # Headshot percentage for this player
            player_hs_percent = (headshots / kills * 100) if kills > 0 else 0
            
            player_value = (
                f"{player_rank_emoji} **#{rank}** • ⏱️ {survival:.1f}m\n"
                f"```css\n"
                f"Combat\n"
                f"━━━━━━━━━━━━━━━━\n"
                f"Kills:      {kills:>3} ({headshots}🎯 {player_hs_percent:.0f}%)\n"
                f"K/D:        {kd_display:>7}\n"
                f"Damage:     {damage:>7,.0f}\n"
                f"Assists:    {assists:>3}\n"
                f"Longest:    {longest_kill:>6.0f}m\n"
                f"\n"
                f"Movement & Items\n"
                f"━━━━━━━━━━━━━━━━\n"
                f"Distance:   {total_dist:>6.2f}km\n"
                f"Heals:      {heals:>3} | Boosts: {boosts:>3}\n"
                f"```"
            )
            
            embed.add_field(
                name=f"👤 {player_name}",
                value=player_value,
                inline=True
            )
        
        # Add footer with match details
        match_id_short = match.get('match_id', 'Unknown')[:12]
        embed.set_footer(
            text=f"Match {match_num}/{total_matches} • ID: {match_id_short}...",
            icon_url="https://raw.githubusercontent.com/pubg/api-assets/master/Assets/Emblems/Emblem_Ranked_01.png"
        )
        
        return embed
    
    def format_time_ago(self, timestamp_str: str) -> str:
        """Format timestamp as 'X hours ago' or 'X minutes ago'"""
        try:
            played_time = datetime.fromisoformat(timestamp_str.replace('Z', '+00:00'))
            now = datetime.now(timezone.utc)
            diff = now - played_time
            
            hours = diff.total_seconds() / 3600
            if hours < 1:
                minutes = int(diff.total_seconds() / 60)
                return f"{minutes} min ago"
            elif hours < 24:
                return f"{int(hours)} hr ago"
            else:
                days = int(hours / 24)
                return f"{days} day{'s' if days > 1 else ''} ago"
        except:
            return "recently"
    
    def run(self):
        """Start the bot"""
        try:
            self.client.run(self.discord_token)
        except Exception as e:
            logger.error(f"❌ Error starting bot: {e}")
            traceback.print_exc()
        finally:
            # Cleanup
            asyncio.run(self.tracker.close_session())


def load_players_from_file(filename: str = "players.txt") -> List[Tuple[str, str]]:
    """Load player names from a text file"""
    if not os.path.exists(filename):
        logger.warning(f"⚠️  '{filename}' not found. Creating example file...")
        with open(filename, 'w', encoding='utf-8') as f:
            f.write("# Add player names here (one per line)\n")
            f.write("# Format: PlayerName or PlayerName,platform\n")
            f.write("# Platforms: steam, psn, xbox, kakao, stadia, console\n")
            f.write("#\n")
            f.write("# Examples:\n")
            f.write("# PlayerName1\n")
            f.write("# PlayerName2,steam\n")
            f.write("# ConsolePlayer,xbox\n")
        logger.info(f"✅ Created '{filename}'. Add player names and run again.")
        return []
    
    players = []
    with open(filename, 'r', encoding='utf-8') as f:
        for line in f:
            line = line.strip()
            if not line or line.startswith('#'):
                continue
            
            if ',' in line:
                name, platform = line.split(',', 1)
                players.append((name.strip(), platform.strip()))
            else:
                players.append((line.strip(), 'steam'))
    
    return players


def load_config(filename: str = "config.json") -> Optional[dict]:
    """Load configuration from JSON file"""
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
    """Main entry point"""
    print("="*80)
    print("PUBG INTEGRATED TRACKER & DISCORD BOT v2.0")
    print("="*80)
    print("Features:")
    print("  ✅ Fully async architecture (no blocking)")
    print("  ✅ Enhanced Discord embeds with detailed stats")
    print("  ✅ Continuous match tracking")
    print("  ✅ Auto-post to Discord")
    print("  ✅ No double-posting (even with multiple players in same match)")
    print("  ✅ Persistent history (survives restarts)")
    print("  ✅ Weekly statistics and leaderboards")
    print("="*80)
    print()
    
    # Load configuration
    config = load_config()
    if not config:
        return
    
    pubg_api_key = config.get('pubg_api_key')
    discord_token = config.get('discord_token')
    channel_id = config.get('discord_channel_id')
    check_interval = config.get('check_interval_seconds', 300)
    request_delay = config.get('request_delay', 7.0)
    max_retries = config.get('max_retries', 3)
    
    # Validate PUBG API key
    if pubg_api_key == "YOUR_PUBG_API_KEY_HERE" or not pubg_api_key:
        logger.error("❌ Please add your PUBG API key to 'config.json'")
        logger.info("   Get your API key from: https://developer.pubg.com/")
        return
    
    # Validate Discord token
    if discord_token == "YOUR_DISCORD_BOT_TOKEN_HERE" or not discord_token:
        logger.error("❌ Please add your Discord bot token to 'config.json'")
        return
    
    # Validate Discord channel ID
    if channel_id == 123456789012345678:
        logger.error("❌ Please add your Discord channel ID to 'config.json'")
        return
    
    # Load players
    players = load_players_from_file()
    if not players:
        logger.warning("\n⚠️  No players found. Add player names to 'players.txt' and run again.")
        return
    
    logger.info(f"📋 Players to track: {len(players)}")
    for idx, (name, platform) in enumerate(players, 1):
        logger.info(f"   {idx}. {name} ({platform})")
    
    logger.info(f"\n⏱️  Settings:")
    logger.info(f"   Check interval: {check_interval}s ({check_interval/60:.1f} minutes)")
    logger.info(f"   Request delay: {request_delay}s")
    logger.info(f"   Discord channel: {channel_id}")
    logger.info(f"\n🚀 Starting integrated bot...")
    logger.info(f"   Press Ctrl+C to stop\n")
    
    # Create and run integrated bot
    bot = IntegratedPUBGBot(
        discord_token=discord_token,
        channel_id=channel_id,
        api_key=pubg_api_key,
        players=players,
        check_interval=check_interval,
        request_delay=request_delay,
        max_retries=max_retries
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