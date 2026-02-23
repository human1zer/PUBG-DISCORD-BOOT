import discord
from datetime import datetime
from typing import Optional


def create_enhanced_match_embed(match: dict, match_num: int, total_matches: int) -> Optional[discord.Embed]:
    all_players_stats = match.get('all_players_stats', {})
    
    if not all_players_stats:
        return None
    
    ranks = [stats.get('rank', 99) for stats in all_players_stats.values()]
    best_rank = min(ranks)
    
    if best_rank == 1:
        color = discord.Color.gold()
        rank_emoji = "🥇"
    elif best_rank <= 3:
        color = discord.Color.from_rgb(192, 192, 192)
        rank_emoji = "🥈"
    elif best_rank <= 5:
        color = discord.Color.from_rgb(205, 127, 50)
        rank_emoji = "🥉"
    elif best_rank <= 10:
        color = discord.Color.blue()
        rank_emoji = "🏅"
    else:
        color = discord.Color.red()
        rank_emoji = "💀"
    
    map_emojis = {
        'Baltic_Main':     '🏔️',
        'Desert_Main':     '🏜️',
        'DihorOtok_Main':  '🏝️',
        'Erangel_Main':    '🌾',
        'Heaven_Main':     '🌸',
        'Kiki_Main':       '🌴',
        'Range_Main':      '🎯',
        'Savage_Main':     '🌴',
        'Summerland_Main': '☀️',
        'Tiger_Main':      '🐯',
        'Chimera_Main':    '🦁',
    }

    map_names = {
        'Baltic_Main':     'Erangel (Old)',
        'Desert_Main':     'Miramar',
        'DihorOtok_Main':  'Vikendi',
        'Erangel_Main':    'Erangel',
        'Heaven_Main':     'Haven',
        'Kiki_Main':       'Deston',
        'Range_Main':      'Training',
        'Savage_Main':     'Sanhok',
        'Summerland_Main': 'Karakin',
        'Tiger_Main':      'Taego',
        'Chimera_Main':    'Paramo',
    }

    map_name = match.get('map', 'Unknown')
    map_emoji = map_emojis.get(map_name, '🗺️')
    map_display = map_names.get(map_name, map_name.replace('_Main', ''))

    player_count = len(all_players_stats)
    category = match.get('match_category', 'MATCH')
    title = f"{rank_emoji} {category} - {player_count} Player{'s' if player_count > 1 else ''}"

    mode_display = match.get('game_mode', 'Unknown').replace('-fpp', ' (FPP)').title()
    description = (
        f"{map_emoji} **{map_display}** • "
        f"🎮 **{mode_display}**\n"
        f"⏱️ Duration: **{match.get('duration_minutes', 0)}** min"
    )
    
    embed = discord.Embed(
        title=title,
        description=description,
        color=color,
        timestamp=datetime.now()
    )
    
    total_kills = sum(stats.get('kills', 0) for stats in all_players_stats.values())
    total_damage = sum(stats.get('damage_dealt', 0) for stats in all_players_stats.values())
    total_headshots = sum(stats.get('headshot_kills', 0) for stats in all_players_stats.values())
    avg_survival = sum(stats.get('survival_time_minutes', 0) for stats in all_players_stats.values()) / len(all_players_stats)
    
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
    
    sorted_players = sorted(
        all_players_stats.items(),
        key=lambda x: (x[1].get('rank', 99), -x[1].get('kills', 0), -x[1].get('damage_dealt', 0))
    )
    
    for player_name, stats in sorted_players:
        rank = stats.get('rank', 'N/A')
        kills = stats.get('kills', 0)
        damage = stats.get('damage_dealt', 0)
        survival = stats.get('survival_time_minutes', 0)
        
        assists = stats.get('assists', 0)
        dbnos = stats.get('dbnos', 0)
        headshots = stats.get('headshot_kills', 0)
        longest_kill = stats.get('longest_kill', 0)
        
        
        heals = stats.get('heals_used', 0)
        boosts = stats.get('boosts_used', 0)
        revives_given    = stats.get('revives', 0)        # ← ADD
        revives_received = stats.get('revives_received', 0)  # ← ADD

        
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
        
        kd_display = f"{kills}/{dbnos}" if rank != 1 else f"{kills}/0"
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
            f"Heals:      {heals:>3} | Boosts: {boosts:>3}\n"
            f"Revives:    {revives_given:>3} given | {revives_received:>3} got\n"  # ← ADD
            f"```"
        )
        
        embed.add_field(
            name=f"👤 {player_name}",
            value=player_value,
            inline=True
        )
    
    match_id_short = match.get('match_id', 'Unknown')[:12]
    embed.set_footer(
        text=f"Match {match_num}/{total_matches} • ID: {match_id_short}...",
        icon_url="https://raw.githubusercontent.com/pubg/api-assets/master/Assets/Emblems/Emblem_Ranked_01.png"
    )
    
    return embed