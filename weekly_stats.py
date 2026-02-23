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
        self.max_history = max_history
        self.history_file = "match_history.json"
        self.history_file = os.path.join(os.path.dirname(os.path.abspath(__file__)), "match_history.json")

    
    def save_match_history(self, new_matches):
        try:
            history = []
            if os.path.exists(self.history_file):
                with open(self.history_file, 'r', encoding='utf-8') as f:
                    history = json.load(f)
            
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
            
            history = history[-self.max_history:]
            
            with open(self.history_file, 'w', encoding='utf-8') as f:
                json.dump(history, f, indent=2)
            
            print(f"💾 Saved {len(history)} matches to history (max: {self.max_history})")
            
        except Exception as e:
            print(f"⚠️ Error saving match history: {e}")
            traceback.print_exc()
    
    def calculate_weekly_best(self, days=7):
        if not os.path.exists(self.history_file):
            print(f"⚠️ No match history found at {self.history_file}")
            return None
        
        try:
            with open(self.history_file, 'r', encoding='utf-8') as f:
                history = json.load(f)
            
            cutoff_time = datetime.now(timezone.utc) - timedelta(days=days)

            EXCLUDED_CATEGORIES = {"CASUAL", "ARCADE"}

            recent_matches = []
            for match in history:
                try:
                    category = match.get('category', '').upper()
                    if any(excl in category for excl in EXCLUDED_CATEGORIES) or 'AIROYALE' in category:
                        continue

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
            
            player_stats = {}
            
            # ── Track ALL longest kill entries per player for top-3 ──────────
            # longest_kills_pool: list of (distance, player_name) across all matches
            longest_kills_pool = []
            
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
                        'total_distance': 0,
                        'longest_kill': 0
                    }
                
                ps = player_stats[player]
                ps['matches'] += 1
                ps['total_kills'] += stats.get('kills', 0)
                ps['total_damage'] += stats.get('damage_dealt', 0)
                ps['total_survival'] += stats.get('survival_time_minutes', 0)
                ps['total_headshots'] += stats.get('headshot_kills', 0)
                ps['total_assists'] += stats.get('assists', 0)
                ps['total_dbnos'] += stats.get('dbnos', 0)
                
                walk = stats.get('walk_distance', 0)
                ride = stats.get('ride_distance', 0)
                ps['total_distance'] += (walk + ride) / 1000
                
                rank = stats.get('rank', 99)
                if rank == 1:
                    ps['wins'] += 1
                if rank <= 5:
                    ps['top_5'] += 1
                if rank <= 10:
                    ps['top_10'] += 1
                
                if stats.get('kills', 0) > ps['best_kills']:
                    ps['best_kills'] = stats.get('kills', 0)
                if stats.get('damage_dealt', 0) > ps['best_damage']:
                    ps['best_damage'] = stats.get('damage_dealt', 0)
                if stats.get('survival_time_minutes', 0) > ps['best_survival']:
                    ps['best_survival'] = stats.get('survival_time_minutes', 0)
                if stats.get('longest_kill', 0) > ps['longest_kill']:
                    ps['longest_kill'] = stats.get('longest_kill', 0)
                
                # Add this match's longest_kill to the global pool
                kill_dist = stats.get('longest_kill', 0)
                if kill_dist > 0:
                    longest_kills_pool.append((kill_dist, player))
            
            # ── Build top-3 longest kills (one entry per player max) ─────────
            # Sort descending, then pick best entry per player, take top 3
            longest_kills_pool.sort(key=lambda x: x[0], reverse=True)
            seen_players = set()
            top3_longest_kills = []
            for dist, pname in longest_kills_pool:
                if pname not in seen_players:
                    top3_longest_kills.append({'player': pname, 'distance': dist})
                    seen_players.add(pname)
                if len(top3_longest_kills) == 3:
                    break
            
            # Calculate averages and score
            for player, stats in player_stats.items():
                matches = stats['matches']
                stats['avg_kills'] = round(stats['total_kills'] / matches, 2)
                stats['avg_damage'] = round(stats['total_damage'] / matches, 2)
                stats['avg_survival'] = round(stats['total_survival'] / matches, 2)
                stats['avg_distance'] = round(stats['total_distance'] / matches, 2)
                stats['win_rate'] = round((stats['wins'] / matches) * 100, 1)
                stats['top_5_rate'] = round((stats['top_5'] / matches) * 100, 1)
                
                stats['score'] = (
                    stats['avg_kills'] * 100 +
                    stats['avg_damage'] * 0.5 +
                    stats['wins'] * 500 +
                    stats['top_5'] * 100 +
                    stats['top_10'] * 50 +
                    stats['avg_survival'] * 10 +
                    stats['total_headshots'] * 20
                )
            
            if not player_stats:
                return None
            
            best_player = max(player_stats.items(), key=lambda x: x[1]['score'])
            
            sorted_players = sorted(
                player_stats.items(),
                key=lambda x: x[1]['score'],
                reverse=True
            )
            
            return {
                'player': best_player[0],
                'stats': best_player[1],
                'top3_longest_kills': top3_longest_kills,   # ← NEW: list of 3
                'all_players': dict(sorted_players),
                'days': days,
                'total_matches': len(recent_matches)
            }
            
        except Exception as e:
            print(f"⚠️ Error calculating weekly best: {e}")
            traceback.print_exc()
            return None
    
    # ──────────────────────────────────────────────────────────────────────────
    #  EMBED BUILDERS
    # ──────────────────────────────────────────────────────────────────────────

    def create_weekly_embed(self, weekly_data):
        player = weekly_data['player']
        stats = weekly_data['stats']
        days = weekly_data['days']
        top3 = weekly_data.get('top3_longest_kills', [])
        
        embed = discord.Embed(
            title=f"🏆 Best Player - Last {days} Days",
            description=f"**{player}** dominated the battlefield!",
            color=discord.Color.gold(),
            timestamp=datetime.now()
        )
        
        embed.add_field(
            name="📋 Matches Played",
            value=f"**Total:** {stats['matches']}\n"
                  f"**Wins:** {stats['wins']} 🏆\n"
                  f"**Top 5:** {stats['top_5']} ({stats['top_5_rate']}%)\n"
                  f"**Win Rate:** {stats['win_rate']}%",
            inline=True
        )
        
        embed.add_field(
            name="⚔️ Combat Stats",
            value=f"**Avg Kills:** {stats['avg_kills']}\n"
                  f"**Best Game:** {stats['best_kills']} kills\n"
                  f"**Total Kills:** {stats['total_kills']}\n"
                  f"**Headshots:** {stats['total_headshots']}",
            inline=True
        )
        
        embed.add_field(
            name="💥 Damage Dealt",
            value=f"**Avg:** {stats['avg_damage']}\n"
                  f"**Best:** {round(stats['best_damage'], 0)}\n"
                  f"**Total:** {round(stats['total_damage'], 0)}",
            inline=True
        )
        
        embed.add_field(
            name="🤝 Support",
            value=f"**Assists:** {stats['total_assists']}\n"
                  f"**Knockdowns:** {stats['total_dbnos']}",
            inline=True
        )
        
        embed.add_field(
            name="⏱️ Survival Time",
            value=f"**Avg:** {stats['avg_survival']} min\n"
                  f"**Best:** {round(stats['best_survival'], 1)} min\n"
                  f"**Total:** {round(stats['total_survival'] / 60, 1)} hours",
            inline=True
        )
        
        embed.add_field(
            name="🗺️ Distance",
            value=f"**Avg:** {stats['avg_distance']} km\n"
                  f"**Total:** {round(stats['total_distance'], 1)} km",
            inline=True
        )
        
        embed.add_field(
            name="🎯 Overall Score",
            value=f"**{round(stats['score'], 0)}** points",
            inline=False
        )
        
        # ── Top 3 Longest Kills ───────────────────────────────────────────────
        medals = ["🥇", "🥈", "🥉"]
        if top3:
            lines = []
            for i, entry in enumerate(top3):
                medal = medals[i] if i < len(medals) else f"{i+1}."
                lines.append(f"{medal} **{entry['player']}**: {round(entry['distance'], 0)}m")
            embed.add_field(
                name="🔭 Top 3 Longest Kills of the Week",
                value="\n".join(lines),
                inline=False
            )
        
        embed.set_footer(text=f"Calculated from {weekly_data['total_matches']} matches")
        
        return embed
    
    def create_leaderboard_embed(self, weekly_data, top_n=5):
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
    
    # ──────────────────────────────────────────────────────────────────────────
    #  TEST MODE  ← NEW
    # ──────────────────────────────────────────────────────────────────────────

    def save_weekly_report_to_txt(self, days=7, output_file="weekly_report_test.txt"):
        """
        Run the full weekly calculation and save the result to a .txt file
        instead of posting to Discord. Useful for local testing anytime.

        Args:
            days: Number of days to look back (default: 7)
            output_file: Path to the output .txt file
        """
        weekly_data = self.calculate_weekly_best(days)
        
        if not weekly_data:
            print("⚠️ No data to write — check your match_history.json")
            return
        
        player  = weekly_data['player']
        stats   = weekly_data['stats']
        top3    = weekly_data.get('top3_longest_kills', [])
        all_pl  = weekly_data['all_players']
        medals  = ["🥇", "🥈", "🥉"]

        lines = []
        sep = "=" * 50

        # ── Header ────────────────────────────────────────────────────────────
        lines.append(sep)
        lines.append(f"  🏆 BEST PLAYER — Last {days} Days")
        lines.append(f"  Generated: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
        lines.append(sep)
        lines.append(f"  Winner: {player}")
        lines.append("")

        # ── Match stats ───────────────────────────────────────────────────────
        lines.append("📋 MATCHES")
        lines.append(f"  Total:    {stats['matches']}")
        lines.append(f"  Wins:     {stats['wins']} 🏆")
        lines.append(f"  Top 5:    {stats['top_5']} ({stats['top_5_rate']}%)")
        lines.append(f"  Win Rate: {stats['win_rate']}%")
        lines.append("")

        # ── Combat ────────────────────────────────────────────────────────────
        lines.append("⚔️ COMBAT")
        lines.append(f"  Avg Kills:    {stats['avg_kills']}")
        lines.append(f"  Best Game:    {stats['best_kills']} kills")
        lines.append(f"  Total Kills:  {stats['total_kills']}")
        lines.append(f"  Headshots:    {stats['total_headshots']}")
        lines.append("")

        # ── Damage ────────────────────────────────────────────────────────────
        lines.append("💥 DAMAGE")
        lines.append(f"  Avg:   {stats['avg_damage']}")
        lines.append(f"  Best:  {round(stats['best_damage'], 0)}")
        lines.append(f"  Total: {round(stats['total_damage'], 0)}")
        lines.append("")

        # ── Support ───────────────────────────────────────────────────────────
        lines.append("🤝 SUPPORT")
        lines.append(f"  Assists:    {stats['total_assists']}")
        lines.append(f"  Knockdowns: {stats['total_dbnos']}")
        lines.append("")

        # ── Survival ──────────────────────────────────────────────────────────
        lines.append("⏱️ SURVIVAL")
        lines.append(f"  Avg:   {stats['avg_survival']} min")
        lines.append(f"  Best:  {round(stats['best_survival'], 1)} min")
        lines.append(f"  Total: {round(stats['total_survival'] / 60, 1)} hours")
        lines.append("")

        # ── Distance ──────────────────────────────────────────────────────────
        lines.append("🗺️ DISTANCE")
        lines.append(f"  Avg:   {stats['avg_distance']} km")
        lines.append(f"  Total: {round(stats['total_distance'], 1)} km")
        lines.append("")

        # ── Score ─────────────────────────────────────────────────────────────
        lines.append(f"🎯 OVERALL SCORE: {round(stats['score'], 0)} points")
        lines.append("")

        # ── Top 3 Longest Kills ───────────────────────────────────────────────
        lines.append("🔭 TOP 3 LONGEST KILLS")
        if top3:
            for i, entry in enumerate(top3):
                medal = medals[i] if i < len(medals) else f"{i+1}."
                lines.append(f"  {medal} {entry['player']}: {round(entry['distance'], 0)}m")
        else:
            lines.append("  No data")
        lines.append("")

        # ── Leaderboard ───────────────────────────────────────────────────────
        lines.append(sep)
        lines.append("  📊 FULL LEADERBOARD")
        lines.append(sep)
        lb_medals = ["🥇", "🥈", "🥉", "4.", "5.", "6.", "7.", "8.", "9.", "10."]
        for idx, (pname, pstats) in enumerate(all_pl.items()):
            m = lb_medals[idx] if idx < len(lb_medals) else f"{idx+1}."
            lines.append(
                f"  {m} {pname:20s}  Score: {round(pstats['score'],0):>8}  "
                f"Matches: {pstats['matches']:>3}  Wins: {pstats['wins']:>3}  "
                f"AvgK: {pstats['avg_kills']:>5}  AvgDmg: {round(pstats['avg_damage'],0):>7}"
            )
        lines.append("")
        lines.append(f"Total matches analysed: {weekly_data['total_matches']}")
        lines.append(sep)

        # ── Write file ────────────────────────────────────────────────────────
        with open(output_file, 'w', encoding='utf-8') as f:
            f.write("\n".join(lines))
        
        print(f"✅ Test report saved to '{output_file}'")

    # ──────────────────────────────────────────────────────────────────────────
    #  PLAYER SUMMARY
    # ──────────────────────────────────────────────────────────────────────────

    def get_player_summary(self, player_name, days=7):
        weekly_data = self.calculate_weekly_best(days)
        if not weekly_data:
            return None
        
        all_players = weekly_data['all_players']
        for player, stats in all_players.items():
            if player.lower() == player_name.lower():
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
        player = player_data['player']
        stats  = player_data['stats']
        rank   = player_data['rank']
        total  = player_data['total_players']
        days   = player_data['days']
        
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
        
        embed.add_field(
            name="🎮 Performance",
            value=f"**Matches:** {stats['matches']}\n"
                  f"**Wins:** {stats['wins']} ({stats['win_rate']}%)\n"
                  f"**Top 5:** {stats['top_5']} ({stats['top_5_rate']}%)\n"
                  f"**Score:** {round(stats['score'], 0)}",
            inline=True
        )
        
        embed.add_field(
            name="⚔️ Combat",
            value=f"**Avg Kills:** {stats['avg_kills']}\n"
                  f"**Best:** {stats['best_kills']} kills\n"
                  f"**Headshots:** {stats['total_headshots']}\n"
                  f"**Avg Dmg:** {round(stats['avg_damage'], 0)}",
            inline=True
        )
        
        embed.add_field(
            name="📈 Stats",
            value=f"**Avg Survival:** {stats['avg_survival']} min\n"
                  f"**Assists:** {stats['total_assists']}\n"
                  f"**KDs:** {stats['total_dbnos']}\n"
                  f"**Distance:** {stats['avg_distance']} km",
            inline=True
        )
        
        return embed


# ══════════════════════════════════════════════════════════════════════════════
#  QUICK TEST — run this file directly:  python weekly_stats.py
# ══════════════════════════════════════════════════════════════════════════════
if __name__ == "__main__":
    import sys

    manager = WeeklyStatsManager()

    # Optional: pass --days N on the command line, e.g.  python weekly_stats.py --days 14
    days = 7
    output = "weekly_report_test.txt"
    for i, arg in enumerate(sys.argv[1:]):
        if arg == "--days" and i + 1 < len(sys.argv) - 1:
            days = int(sys.argv[i + 2])
        if arg == "--out" and i + 1 < len(sys.argv) - 1:
            output = sys.argv[i + 2]

    print(f"🧪 Running test mode (last {days} days) → {output}")
    manager.save_weekly_report_to_txt(days=days, output_file=output)

    