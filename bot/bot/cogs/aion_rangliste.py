"""AION-2: `/dungeon-rangliste` zeigt Bestzeiten und die DPS-Rangliste eines Dungeons.

Die Daten sammelt `aion_dedup.py` aus den Runs des NexBoards (gespeichert über aion_records.py).
`/rangliste` ist schon die Rangliste des Levelsystems, daher der längere Name.
"""

from __future__ import annotations

from datetime import datetime

import discord
from discord import app_commands
from discord.ext import commands

from ..aion_format import fmt_dps, fmt_time
from ..aion_records import RunRecords
from ..errors import UserError

# Ein Vorschlag beim Tippen trägt Dungeon und Schwierigkeit in einem Wert, durch Tab getrennt
# (kommt in keinem Dungeon-Namen vor).
SEPARATOR = "\t"
MEDALS = ["🥇", "🥈", "🥉"]


def dungeon_label(dungeon: str, difficulty: str) -> str:
    return f"{dungeon} ({difficulty})" if difficulty else dungeon


def place_mark(index: int) -> str:
    return MEDALS[index] if index < len(MEDALS) else f"**#{index + 1}**"


def ranking_embed(title: str, times: list, players: list) -> discord.Embed:
    """Schnellste Runs und Spieler nach bester DPS, als ein Embed."""
    time_lines = []
    for i, r in enumerate(times):
        day = datetime.fromtimestamp(r["created"]).strftime("%d.%m.")
        time_lines.append(f"{place_mark(i)} **{fmt_time(r['fight_ms'])}** · {day} · {r['players']}")
    player_lines = []
    for i, p in enumerate(players):
        cls = f" ({p['class']})" if p["class"] else ""
        player_lines.append(f"{place_mark(i)} {p['player']}{cls} · **{fmt_dps(p['dps'])}**")
    e = discord.Embed(title=f"🏆 {title}", colour=discord.Colour.gold())
    e.add_field(name="🏁 Bestzeiten", value="\n".join(time_lines) or "–", inline=False)
    e.add_field(name="⚔️ Beste DPS", value="\n".join(player_lines) or "–", inline=False)
    e.set_footer(text="Nur vollständige Runs, alle Bosse besiegt")
    return e


class AionRangliste(commands.Cog):
    def __init__(self, bot):
        self.records = RunRecords(bot.db)

    @app_commands.command(name="dungeon-rangliste", description="Bestzeiten und DPS-Rangliste eines Dungeons")
    @app_commands.describe(dungeon="Dungeon und Schwierigkeit, Vorschläge beim Tippen")
    @app_commands.guild_only()
    async def ranking(self, interaction: discord.Interaction, dungeon: str):
        name, difficulty = await self._resolve(interaction.guild_id, dungeon)
        times, players = await self.records.ranking(interaction.guild_id, name, difficulty)
        if not times:
            raise UserError(f"Für „{dungeon_label(name, difficulty)}“ gibt es noch keinen vollständigen Run.")
        embed = ranking_embed(dungeon_label(name, difficulty), times, players)
        await interaction.response.send_message(embed=embed)

    @ranking.autocomplete("dungeon")
    async def ranking_autocomplete(self, interaction: discord.Interaction, current: str):
        found = await self.records.dungeons(interaction.guild_id, current)
        return [
            app_commands.Choice(name=dungeon_label(name, difficulty)[:100], value=f"{name}{SEPARATOR}{difficulty}")
            for name, difficulty in found
        ]

    async def _resolve(self, guild_id: int, value: str) -> tuple[str, str]:
        """Gewählter Vorschlag, oder ohne Auswahl der erste Dungeon, der zum Getippten passt."""
        if SEPARATOR in value:
            name, difficulty = value.split(SEPARATOR, 1)
            return name, difficulty
        found = await self.records.dungeons(guild_id, value.strip())
        if not found:
            raise UserError(f"Kein Dungeon „{value}“ mit gewerteten Runs.")
        return found[0]


async def setup(bot):
    await bot.add_cog(AionRangliste(bot))
