"""Slash-Befehle der Runs: /aion (Kanal, Wartezeit, Token) und /dungeon-rangliste (Bestzeiten und
DPS-Rangliste eines Dungeons). `/rangliste` gehört schon dem Levelsystem, daher der längere Name."""

from __future__ import annotations

from datetime import datetime
from typing import TYPE_CHECKING

import discord
from discord import app_commands

from bot.core import ModuleCog
from bot.errors import UserError

from .format import fmt_dps, fmt_time
from .records import DungeonKey, FastRun, PlayerBest

if TYPE_CHECKING:
    from .posts import RunPosts

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


class RunsCog(ModuleCog):
    module: "RunPosts"

    @app_commands.command(name="aion", description="AION-2-Posts aus dem NexBoard einrichten")
    @app_commands.describe(
        kanal="Kanal für die zusammengeführten AION-Posts",
        wartezeit="Sekunden, die auf weitere Meldungen vom selben Lauf gewartet wird (Standard 15)",
        token="Neuen API-Token erzeugen (alten ungültig machen)",
        aus="AION-Posts abschalten",
    )
    @app_commands.default_permissions(manage_guild=True)
    @app_commands.guild_only()
    async def aion_settings(self, interaction: discord.Interaction, kanal: discord.TextChannel | None = None,
                            wartezeit: app_commands.Range[int, 5, 300] | None = None, token: bool = False,
                            aus: bool = False) -> None:
        guild = interaction.guild
        assert guild is not None  # guild_only
        db = self.module.db
        if aus:
            await db.set(guild.id, "aion_channel", None)
            await interaction.response.send_message("AION-Posts sind aus.", ephemeral=True)
            return
        if kanal:
            await db.set(guild.id, "aion_channel", kanal.id)
        if wartezeit:
            await db.set(guild.id, "aion_dedup_delay", wartezeit)
        channel = guild.get_channel(db.get_int(guild.id, "aion_channel") or 0)
        if channel is None:
            await interaction.response.send_message("Noch kein Kanal festgelegt. `/aion kanal:#dein-aion-kanal`.",
                                                    ephemeral=True)
            return
        api_token = await self.module.token(guild.id, renew=token)
        await interaction.response.send_message(
            f"Kanal: {channel.mention}, Wartezeit {self.module.delay(guild.id)}s.\n\n"
            f"Im NexBoard unter Discord-Bot eintragen:\n`{self.module.api_url()}`\nToken: `{api_token}`\n"
            "Geheim halten, nur an NexBoards geben, die mitmachen sollen. Mit `token:True` einen neuen "
            "erzeugen (macht den alten ungültig).", ephemeral=True)

    @app_commands.command(name="dungeon-rangliste", description="Bestzeiten und DPS-Rangliste eines Dungeons")
    @app_commands.describe(dungeon="Dungeon und Schwierigkeit, Vorschläge beim Tippen")
    @app_commands.guild_only()
    async def ranking(self, interaction: discord.Interaction, dungeon: str) -> None:
        assert interaction.guild_id is not None  # guild_only
        key = await self._resolve(interaction.guild_id, dungeon)
        runs = await self.module.records.fastest(key)
        if not runs:
            raise UserError(f"Für „{dungeon_label(key)}“ gibt es noch keinen vollständigen Run.")
        players = await self.module.records.best_players(key)
        await interaction.response.send_message(embed=ranking_embed(dungeon_label(key), runs, players))

    @ranking.autocomplete("dungeon")
    async def ranking_autocomplete(
        self, interaction: discord.Interaction, current: str,
    ) -> list[app_commands.Choice[str]]:
        if interaction.guild_id is None:
            return []
        keys = await self.module.records.dungeons(interaction.guild_id, current)
        return [
            app_commands.Choice(name=dungeon_label(k)[:MAX_CHOICE_NAME], value=f"{k.dungeon}{SEPARATOR}{k.difficulty}")
            for k in keys
        ]

    async def _resolve(self, guild_id: int, value: str) -> DungeonKey:
        """Gewählter Vorschlag, oder ohne Auswahl der erste Dungeon, der zum Getippten passt."""
        if SEPARATOR in value:
            dungeon, difficulty = value.split(SEPARATOR, 1)
            return DungeonKey(guild_id, dungeon, difficulty)
        keys = await self.module.records.dungeons(guild_id, value.strip())
        if not keys:
            raise UserError(f"Kein Dungeon „{value}“ mit gewerteten Runs.")
        return keys[0]
