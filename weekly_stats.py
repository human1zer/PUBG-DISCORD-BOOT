"""
Weekly Stats Module for PUBG Bot
Handles match history tracking and weekly best player calculations
"""

import json
import os
import traceback
from datetime import datetime, timedelta, timezone
import discord


class WeeklyStatsManager:
    """Manages match history and weekly statistics"""
    
    def __init__(self, max_history=500):
        """
        Initialize stats manager
        
        Args:
            max_history: Maximum number of matches to keep in history
        """
        self.max_history = max_history
        self.history_file = "match_history.json"
    
    def save_match_history(self, new_matches):
        """
        Save detailed match history for stats tracking
        
        Args:
            new_matches: List of match data dictionaries from tracker
        """
        try:
            # Load existing history
            history = []
            if os.path.exists(self.history_file):
                with open(self.history_file, 'r', encoding='utf-8') as f:
                    history = json.load(f)
            
            # Add new matches from this cycle
            for match in new_matches:
                history.append({
                    'match_id': match['match_id'],
                    'player_name': match['player_name'],
                    'timestamp': match['played_at'],
                    'stats': match['player_stats'],
                    'map': match['map'],
                    'mode': match['game_mode'],
                    'category': match['match_category']
                })
            
            # Keep only recent matches
            history = history[-self.max_history:]
            
            # Save
            with open(self.history_file, 'w', encoding='utf-8') as f:
                json.dump(history, f, indent=2)
            
            print(f"💾 Saved {len(history)} matches to history (max: {self.max_history})")
            
        except Exception as e:
            print(f"⚠️ Error saving match history: {e}")
            traceback.print_exc()
    
    def calculate_weekly_best(self, days=7):
        """
        Find the best player from the last N days
        
        Args:
            days: Number of days to look back (default: 7)
            
        Returns:
            Dictionary with best player stats or None
        """
        if not os.path.exists(self.history_file):
            print(f"⚠️ No match history found at {self.history_file}")
            return None
        
        try:
            with open(self.history_file, 'r', encoding='utf-8') as f:
                history = json.load(f)
            
            from datetime import timezone
            cutoff_time = datetime.now(timezone.utc) - timedelta(days=days)
            
            # Filter matches from last N days
            recent_matches = []
            for match in history:
                try:
                    match_time = datetime.fromisoformat(match['timestamp'].replace('Z', '+00:00'))
                    if match_time >= cutoff_time:
                        recent_matches.append(match)
                except Exception as e:
                    print(f"⚠️ Error parsing timestamp: {e}")
                    continue
            
            if not recent_matches:
                print(f"⚠️ No matches found in the last {days} days")
                return None
            
            print(f"📊 Analyzing {len(recent_matches)} matches from the last {days} days...")
            
            # Calculate stats per player
            player_stats = {}
            
            for match in recent_matches:
                player = match['player_name']
                stats = match['stats']
                
                if player not in player_stats:
                    player_stats[player] = {
                        'matches': 0,
                        'total_kills': 0,
                        'total_damage': 0,
                        'total_survival': 0,
                        'wins': 0,
                        'top_5': 0,
                        'top_10': 0,
                        'total_headshots': 0,
                        'total_assists': 0,
                        'total_dbnos': 0,
                        'best_kills': 0,
                        'best_damage': 0,
                        'best_survival': 0,
                        'total_distance': 0
                    }
                
                ps = player_stats[player]
                ps['matches'] += 1
                ps['total_kills'] += stats.get('kills', 0)
                ps['total_damage'] += stats.get('damage_dealt', 0)
                ps['total_survival'] += stats.get('survival_time_minutes', 0)
                ps['total_headshots'] += stats.get('headshot_kills', 0)
                ps['total_assists'] += stats.get('assists', 0)
                ps['total_dbnos'] += stats.get('dbnos', 0)
                
                # Distance traveled
                walk = stats.get('walk_distance', 0)
                ride = stats.get('ride_distance', 0)
                ps['total_distance'] += (walk + ride) / 1000  # Convert to km
                
                # Rankings
                rank = stats.get('rank', 99)
                if rank == 1:
                    ps['wins'] += 1
                if rank <= 5:
                    ps['top_5'] += 1
                if rank <= 10:
                    ps['top_10'] += 1
                
                # Track best performances
                if stats.get('kills', 0) > ps['best_kills']:
                    ps['best_kills'] = stats.get('kills', 0)
                if stats.get('damage_dealt', 0) > ps['best_damage']:
                    ps['best_damage'] = stats.get('damage_dealt', 0)
                if stats.get('survival_time_minutes', 0) > ps['best_survival']:
                    ps['best_survival'] = stats.get('survival_time_minutes', 0)
            
            # Calculate averages and score
            for player, stats in player_stats.items():
                matches = stats['matches']
                stats['avg_kills'] = round(stats['total_kills'] / matches, 2)
                stats['avg_damage'] = round(stats['total_damage'] / matches, 2)
                stats['avg_survival'] = round(stats['total_survival'] / matches, 2)
                stats['avg_distance'] = round(stats['total_distance'] / matches, 2)
                stats['win_rate'] = round((stats['wins'] / matches) * 100, 1)
                stats['top_5_rate'] = round((stats['top_5'] / matches) * 100, 1)
                
                # Calculate overall score (weighted)
                # You can adjust these weights to your preference
                stats['score'] = (
                    stats['avg_kills'] * 100 +           # Kills are important
                    stats['avg_damage'] * 0.5 +          # Damage matters
                    stats['wins'] * 500 +                # Wins are very valuable
                    stats['top_5'] * 100 +               # Top 5 finishes
                    stats['top_10'] * 50 +               # Top 10 finishes
                    stats['avg_survival'] * 10 +         # Survival time
                    stats['total_headshots'] * 20        # Headshots bonus
                )
            
            # Find best player
            if not player_stats:
                return None
            
            best_player = max(player_stats.items(), key=lambda x: x[1]['score'])
            
            # Sort all players by score
            sorted_players = sorted(
                player_stats.items(), 
                key=lambda x: x[1]['score'], 
                reverse=True
            )
            
            return {
                'player': best_player[0],
                'stats': best_player[1],
                'all_players': dict(sorted_players),
                'days': days,
                'total_matches': len(recent_matches)
            }
            
        except Exception as e:
            print(f"⚠️ Error calculating weekly best: {e}")
            traceback.print_exc()
            return None
    
    def create_weekly_embed(self, weekly_data):
        """
        Create Discord embed for weekly best player
        
        Args:
            weekly_data: Dictionary returned from calculate_weekly_best()
            
        Returns:
            discord.Embed object
        """
        player = weekly_data['player']
        stats = weekly_data['stats']
        days = weekly_data['days']
        
        embed = discord.Embed(
            title=f"🏆 Best Player - Last {days} Days",
            description=f"**{player}** dominated the battlefield!",
            color=discord.Color.gold(),
            timestamp=datetime.now()
        )
        
        # Match stats
        embed.add_field(
            name="📋 Matches Played",
            value=f"**Total:** {stats['matches']}\n"
                  f"**Wins:** {stats['wins']} 🏆\n"
                  f"**Top 5:** {stats['top_5']} ({stats['top_5_rate']}%)\n"
                  f"**Win Rate:** {stats['win_rate']}%",
            inline=True
        )
        
        # Combat stats
        embed.add_field(
            name="⚔️ Combat Stats",
            value=f"**Avg Kills:** {stats['avg_kills']}\n"
                  f"**Best Game:** {stats['best_kills']} kills\n"
                  f"**Total Kills:** {stats['total_kills']}\n"
                  f"**Headshots:** {stats['total_headshots']}",
            inline=True
        )
        
        # Damage stats
        embed.add_field(
            name="💥 Damage Dealt",
            value=f"**Avg:** {stats['avg_damage']}\n"
                  f"**Best:** {round(stats['best_damage'], 0)}\n"
                  f"**Total:** {round(stats['total_damage'], 0)}",
            inline=True
        )
        
        # Support stats
        embed.add_field(
            name="🤝 Support",
            value=f"**Assists:** {stats['total_assists']}\n"
                  f"**Knockdowns:** {stats['total_dbnos']}",
            inline=True
        )
        
        # Survival
        embed.add_field(
            name="⏱️ Survival Time",
            value=f"**Avg:** {stats['avg_survival']} min\n"
                  f"**Best:** {round(stats['best_survival'], 1)} min\n"
                  f"**Total:** {round(stats['total_survival'] / 60, 1)} hours",
            inline=True
        )
        
        # Movement
        embed.add_field(
            name="🗺️ Distance",
            value=f"**Avg:** {stats['avg_distance']} km\n"
                  f"**Total:** {round(stats['total_distance'], 1)} km",
            inline=True
        )
        
        # Score
        embed.add_field(
            name="🎯 Overall Score",
            value=f"**{round(stats['score'], 0)}** points",
            inline=False
        )
        
        embed.set_footer(text=f"Calculated from {weekly_data['total_matches']} matches")
        
        return embed
    
    def create_leaderboard_embed(self, weekly_data, top_n=5):
        """
        Create a leaderboard embed showing top N players
        
        Args:
            weekly_data: Dictionary returned from calculate_weekly_best()
            top_n: Number of top players to show (default: 5)
            
        Returns:
            discord.Embed object
        """
        days = weekly_data['days']
        all_players = weekly_data['all_players']
        
        embed = discord.Embed(
            title=f"📊 Leaderboard - Last {days} Days",
            description=f"Top {min(top_n, len(all_players))} Players",
            color=discord.Color.blue(),
            timestamp=datetime.now()
        )
        
        medals = ["🥇", "🥈", "🥉", "4️⃣", "5️⃣", "6️⃣", "7️⃣", "8️⃣", "9️⃣", "🔟"]
        
        for idx, (player, stats) in enumerate(list(all_players.items())[:top_n]):
            medal = medals[idx] if idx < len(medals) else f"{idx+1}."
            
            embed.add_field(
                name=f"{medal} {player}",
                value=f"**Score:** {round(stats['score'], 0)}\n"
                      f"**Matches:** {stats['matches']} | **Wins:** {stats['wins']}\n"
                      f"**Avg K/D:** {stats['avg_kills']} | **Dmg:** {round(stats['avg_damage'], 0)}",
                inline=False
            )
        
        embed.set_footer(text=f"Based on {weekly_data['total_matches']} total matches")
        
        return embed
    
    def get_player_summary(self, player_name, days=7):
        """
        Get individual player stats for the last N days
        
        Args:
            player_name: Name of the player
            days: Number of days to look back
            
        Returns:
            Dictionary with player stats or None
        """
        weekly_data = self.calculate_weekly_best(days)
        
        if not weekly_data:
            return None
        
        all_players = weekly_data['all_players']
        
        for player, stats in all_players.items():
            if player.lower() == player_name.lower():
                # Find rank
                rank = list(all_players.keys()).index(player) + 1
                
                return {
                    'player': player,
                    'stats': stats,
                    'rank': rank,
                    'total_players': len(all_players),
                    'days': days
                }
        
        return None
    
    def create_player_summary_embed(self, player_data):
        """
        Create embed for individual player summary
        
        Args:
            player_data: Dictionary from get_player_summary()
            
        Returns:
            discord.Embed object
        """
        player = player_data['player']
        stats = player_data['stats']
        rank = player_data['rank']
        total = player_data['total_players']
        days = player_data['days']
        
        # Determine color based on rank
        if rank == 1:
            color = discord.Color.gold()
        elif rank <= 3:
            color = discord.Color.green()
        elif rank <= 5:
            color = discord.Color.blue()
        else:
            color = discord.Color.greyple()
        
        embed = discord.Embed(
            title=f"📊 {player} - {days} Day Summary",
            description=f"Rank: **#{rank}** out of {total} players",
            color=color,
            timestamp=datetime.now()
        )
        
        # Performance overview
        embed.add_field(
            name="🎮 Performance",
            value=f"**Matches:** {stats['matches']}\n"
                  f"**Wins:** {stats['wins']} ({stats['win_rate']}%)\n"
                  f"**Top 5:** {stats['top_5']} ({stats['top_5_rate']}%)\n"
                  f"**Score:** {round(stats['score'], 0)}",
            inline=True
        )
        
        # Combat
        embed.add_field(
            name="⚔️ Combat",
            value=f"**Avg Kills:** {stats['avg_kills']}\n"
                  f"**Best:** {stats['best_kills']} kills\n"
                  f"**Headshots:** {stats['total_headshots']}\n"
                  f"**Avg Dmg:** {round(stats['avg_damage'], 0)}",
            inline=True
        )
        
        # Other
        embed.add_field(
            name="📈 Stats",
            value=f"**Avg Survival:** {stats['avg_survival']} min\n"
                  f"**Assists:** {stats['total_assists']}\n"
                  f"**KDs:** {stats['total_dbnos']}\n"
                  f"**Distance:** {stats['avg_distance']} km",
            inline=True
        )
        
        return embed