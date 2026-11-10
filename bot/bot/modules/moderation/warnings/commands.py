"""Slash-Befehle für Verwarnungen und Strafen."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import TYPE_CHECKING

import discord
from discord import app_commands

from bot.core import ModuleCog
from bot.core.moderation import clip
from bot.errors import UserError

if TYPE_CHECKING:
    from . import Warnings

MAX_EMBED = 4000
REASON_PREVIEW = 200


def guild_of(interaction: discord.Interaction) -> discord.Guild:
    if interaction.guild is None:
        raise UserError("Das geht nur auf einem Server.")
    return interaction.guild


class WarningsCog(ModuleCog):
    module: "Warnings"

    @app_commands.command(name="warn", description="Mitglied verwarnen, mit Grund")
    @app_commands.describe(grund="Wird im Log und in der Verwarnung selbst vermerkt")
    @app_commands.default_permissions(moderate_members=True)
    @app_commands.guild_only()
    async def warn(self, interaction: discord.Interaction, mitglied: discord.Member, grund: str) -> None:
        count = await self.module.warn(guild_of(interaction), mitglied, interaction.user, grund)
        await interaction.response.send_message(f"{mitglied.mention} verwarnt (Nr. {count}). Grund: {grund}",
                                                ephemeral=True)

    @app_commands.command(name="warnungen", description="Verwarnungen eines Mitglieds anzeigen")
    @app_commands.default_permissions(moderate_members=True)
    @app_commands.guild_only()
    async def warnings_list(self, interaction: discord.Interaction, mitglied: discord.Member) -> None:
        guild = guild_of(interaction)
        rows = await self.module.store.of_member(guild.id, mitglied.id)
        if not rows:
            await interaction.response.send_message(f"{mitglied.mention} hat keine Verwarnungen.", ephemeral=True)
            return
        lines = []
        for r in rows:
            mod = guild.get_member(r["moderator_id"])
            when = discord.utils.format_dt(datetime.fromtimestamp(r["created"], tz=UTC), "R")
            lines.append(f"**#{r['id']}** {when} – {clip(r['reason'], REASON_PREVIEW)} "
                         f"(von {mod.mention if mod else r['moderator_id']})")
        embed = discord.Embed(title=f"⚠️ {len(rows)} Verwarnung(en): {mitglied}", colour=discord.Colour.yellow(),
                              description="\n".join(lines)[:MAX_EMBED])
        await interaction.response.send_message(embed=embed, ephemeral=True)

    @app_commands.command(name="warnung-loeschen",
                          description="Einzelne Verwarnung per ID löschen (siehe /warnungen)")
    @app_commands.default_permissions(moderate_members=True)
    @app_commands.guild_only()
    async def warn_delete(self, interaction: discord.Interaction, warnung_id: int) -> None:
        await self.module.store.delete(guild_of(interaction).id, warnung_id)
        await interaction.response.send_message(f"Verwarnung #{warnung_id} gelöscht.", ephemeral=True)

    @app_commands.command(name="timeout", description="Mitglied für eine Weile stummschalten")
    @app_commands.describe(minuten="Dauer (1–40320 = 4 Wochen)", grund="Wird im Log vermerkt")
    @app_commands.default_permissions(moderate_members=True)
    @app_commands.guild_only()
    async def timeout_cmd(self, interaction: discord.Interaction, mitglied: discord.Member,
                          minuten: app_commands.Range[int, 1, 40320], grund: str | None = None) -> None:
        await self.module.timeout(mitglied, minuten, str(interaction.user), grund)
        await interaction.response.send_message(f"{mitglied.mention} ist für {minuten} Min. stumm.", ephemeral=True)

    @app_commands.command(name="kick", description="Mitglied vom Server entfernen (kann wieder beitreten)")
    @app_commands.describe(grund="Wird im Log vermerkt")
    @app_commands.default_permissions(kick_members=True)
    @app_commands.guild_only()
    async def kick(self, interaction: discord.Interaction, mitglied: discord.Member, grund: str | None = None) -> None:
        await self.module.kick(mitglied, str(interaction.user), grund)
        await interaction.response.send_message(f"{mitglied.mention} wurde entfernt.", ephemeral=True)

    @app_commands.command(name="ban", description="Mitglied bannen")
    @app_commands.describe(grund="Wird im Log vermerkt",
                           nachrichten_tage="Nachrichten der letzten X Tage mitlöschen (0–7)")
    @app_commands.default_permissions(ban_members=True)
    @app_commands.guild_only()
    async def ban(self, interaction: discord.Interaction, mitglied: discord.Member, grund: str | None = None,
                  nachrichten_tage: app_commands.Range[int, 0, 7] = 0) -> None:
        await self.module.ban(mitglied, str(interaction.user), grund, nachrichten_tage)
        await interaction.response.send_message(f"{mitglied.mention} wurde gebannt.", ephemeral=True)

    @app_commands.command(name="unban",
                          description="Bann aufheben (User-ID, siehe /aufraeumen bericht oder Bann-Liste)")
    @app_commands.default_permissions(ban_members=True)
    @app_commands.guild_only()
    async def unban(self, interaction: discord.Interaction, user_id: str, grund: str | None = None) -> None:
        if not user_id.isdigit():
            raise UserError("Das ist keine gültige User-ID.")
        await self.module.unban(guild_of(interaction), int(user_id), f"{interaction.user}: {grund or 'ohne Grund'}")
        await interaction.response.send_message(f"Bann für `{user_id}` aufgehoben.", ephemeral=True)
