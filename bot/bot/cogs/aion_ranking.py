"""AION-2: `/dungeon-rangliste` zeigt Bestzeiten und die DPS-Rangliste eines Dungeons.

Die Daten sammelt `aion_dedup.py` aus den Runs des NexBoards (gespeichert über aion_records.py).
`/rangliste` ist schon die Rangliste des Levelsystems, daher der längere Name.
"""

from __future__ import annotations

from datetime import datetime
from typing import TYPE_CHECKING

import discord
from discord import app_commands
from discord.ext import commands

from ..aion_format import fmt_dps, fmt_time
from ..aion_records import DungeonKey, FastRun, PlayerBest, RunRecords
from ..errors import UserError

if TYPE_CHECKING:  # nur für die Typprüfung, der Bot lädt diese Datei selbst
    from ..__main__ import Bot

# Ein Vorschlag beim Tippen trägt Dungeon und Schwierigkeit in einem Wert, durch Tab getrennt
# (kommt in keinem Dungeon-Namen vor).
SEPARATOR = "\t"
MEDALS = ("🥇", "🥈", "🥉")
MAX_CHOICE_NAME = 100  # Discords Grenze für den Text eines Vorschlags


def dungeon_label(key: DungeonKey) -> str:
    return f"{key.dungeon} ({key.difficulty})" if key.difficulty else key.dungeon


def place_mark(index: int) -> str:
    return MEDALS[index] if index < len(MEDALS) else f"**#{index + 1}**"


def fast_run_line(index: int, run: FastRun) -> str:
    day = datetime.fromtimestamp(run.created).strftime("%d.%m.")
    return f"{place_mark(index)} **{fmt_time(run.fight_ms)}** · {day} · {run.players}"


def player_line(index: int, best: PlayerBest) -> str:
    player_class = f" ({best.player_class})" if best.player_class else ""
    return f"{place_mark(index)} {best.player}{player_class} · **{fmt_dps(best.dps)}**"


def ranking_embed(title: str, runs: list[FastRun], players: list[PlayerBest]) -> discord.Embed:
    """Schnellste Runs und Spieler nach bester DPS, als ein Embed."""
    run_lines = [fast_run_line(i, r) for i, r in enumerate(runs)]
    player_lines = [player_line(i, p) for i, p in enumerate(players)]
    embed = discord.Embed(title=f"🏆 {title}", colour=discord.Colour.gold())
    embed.add_field(name="🏁 Bestzeiten", value="\n".join(run_lines) or "–", inline=False)
    embed.add_field(name="⚔️ Beste DPS", value="\n".join(player_lines) or "–", inline=False)
    embed.set_footer(text="Nur vollständige Runs, alle Bosse besiegt")
    return embed


class AionRanking(commands.Cog):
    def __init__(self, records: RunRecords) -> None:
        self.records = records

    @app_commands.command(name="dungeon-rangliste", description="Bestzeiten und DPS-Rangliste eines Dungeons")
    @app_commands.describe(dungeon="Dungeon und Schwierigkeit, Vorschläge beim Tippen")
    @app_commands.guild_only()
    async def ranking(self, interaction: discord.Interaction, dungeon: str) -> None:
        assert interaction.guild_id is not None  # guild_only
        key = await self._resolve(interaction.guild_id, dungeon)
        runs = await self.records.fastest(key)
        if not runs:
            raise UserError(f"Für „{dungeon_label(key)}“ gibt es noch keinen vollständigen Run.")
        players = await self.records.best_players(key)
        await interaction.response.send_message(embed=ranking_embed(dungeon_label(key), runs, players))

    @ranking.autocomplete("dungeon")
    async def ranking_autocomplete(
        self, interaction: discord.Interaction, current: str,
    ) -> list[app_commands.Choice[str]]:
        if interaction.guild_id is None:
            return []
        keys = await self.records.dungeons(interaction.guild_id, current)
        return [
            app_commands.Choice(name=dungeon_label(k)[:MAX_CHOICE_NAME], value=f"{k.dungeon}{SEPARATOR}{k.difficulty}")
            for k in keys
        ]

    async def _resolve(self, guild_id: int, value: str) -> DungeonKey:
        """Gewählter Vorschlag, oder ohne Auswahl der erste Dungeon, der zum Getippten passt."""
        if SEPARATOR in value:
            dungeon, difficulty = value.split(SEPARATOR, 1)
            return DungeonKey(guild_id, dungeon, difficulty)
        keys = await self.records.dungeons(guild_id, value.strip())
        if not keys:
            raise UserError(f"Kein Dungeon „{value}“ mit gewerteten Runs.")
        return keys[0]


async def setup(bot: Bot) -> None:
    await bot.add_cog(AionRanking(RunRecords(bot.db)))
