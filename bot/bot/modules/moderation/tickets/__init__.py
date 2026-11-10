"""Tickets: Panel mit Knöpfen (Frage, Meldung, Bewerbung) öffnet einen privaten Thread mit dem Team.

Panel-Knöpfe und „Schließen“ im Thread haben feste custom_ids und laufen über on_interaction, sie
funktionieren also auch nach einem Neustart. Beim Schließen geht der Verlauf als Datei in den Log-Kanal.
"""

from __future__ import annotations

import io
import time
from typing import Any, ClassVar

import discord
from discord.ext import commands
from nexcore import ModuleInfo

from bot.core import BotContext, BotModule, GuildSettings
from bot.core.moderation import LOG, LogEntry
from bot.core.module import Listener
from bot.db import Database

from .settings import TicketSettings

PANEL_PREFIX = "ticket:open:"
CLOSE_ID = "ticket:close"
HISTORY_LIMIT = 500
MAX_NAME = 100
# Art → (Emoji, Beschriftung, Feld im Formular)
KINDS = {
    "frage": ("❓", "Frage", "Frage"),
    "meldung": ("⚠️", "Meldung", "Was melden?"),
    "bewerbung": ("📋", "Bewerbung", "Kurz zu dir"),
}


class TicketStore:
    def __init__(self, db: Database) -> None:
        self.db = db

    async def add(self, thread_id: int, guild_id: int, user_id: int, kind: str) -> None:
        await self.db.execute(
            "INSERT INTO tickets (channel_id, guild_id, user_id, kind, created) VALUES (?, ?, ?, ?, ?)",
            (thread_id, guild_id, user_id, kind, time.time()))

    async def get(self, thread_id: int) -> Any:
        return await self.db.fetchone("SELECT * FROM tickets WHERE channel_id=?", (thread_id,))

    async def close(self, thread_id: int) -> None:
        await self.db.execute("UPDATE tickets SET closed=? WHERE channel_id=?", (time.time(), thread_id))


async def transcript(thread: discord.Thread) -> discord.File:
    lines = []
    async for m in thread.history(limit=HISTORY_LIMIT, oldest_first=True):
        when = time.strftime("%Y-%m-%d %H:%M", time.localtime(m.created_at.timestamp()))
        lines.append(f"[{when}] {m.author}: {m.content}")
    text = "\n".join(lines) or "(keine Nachrichten)"
    return discord.File(io.BytesIO(text.encode()), filename=f"ticket-{thread.id}.txt")


class Tickets(BotModule):
    info: ClassVar[ModuleInfo] = ModuleInfo(
        id="moderation.tickets", name="Tickets", category="Moderation", icon="mdi-ticket",
        summary="Panel, über das Mitglieder einen privaten Thread mit dem Team öffnen.",
    )
    Settings = TicketSettings

    def __init__(self, ctx: BotContext) -> None:
        super().__init__(ctx)
        self.settings = GuildSettings(ctx.db, TicketSettings)
        self.store = TicketStore(ctx.db)

    def listeners(self) -> dict[str, Listener]:
        return {"on_interaction": self.on_interaction}

    def cog(self) -> commands.Cog:
        from .commands import TicketsCog

        return TicketsCog(self)

    def team(self, guild: discord.Guild) -> list[discord.Role]:
        roles = (guild.get_role(rid) for rid in self.settings.get(guild.id).ticket_team_roles)
        return [r for r in roles if r is not None]

    async def on_interaction(self, interaction: discord.Interaction) -> None:
        if interaction.type is not discord.InteractionType.component or interaction.data is None:
            return
        custom_id = str(interaction.data.get("custom_id", ""))
        kind = custom_id.removeprefix(PANEL_PREFIX)
        if custom_id.startswith(PANEL_PREFIX) and kind in KINDS:
            from .views import TicketModal

            await interaction.response.send_modal(TicketModal(self, kind))
        elif custom_id == CLOSE_ID:
            await self.close(interaction)

    async def open(self, interaction: discord.Interaction, kind: str, text: str) -> None:
        guild, channel, user = interaction.guild, interaction.channel, interaction.user
        if guild is None or not isinstance(channel, discord.TextChannel):
            return
        roles = self.team(guild)
        problem = self.cannot_open(channel, roles)
        if problem:
            await interaction.response.send_message(problem, ephemeral=True)
            return
        emoji, label, _ = KINDS[kind]
        await interaction.response.defer(ephemeral=True, thinking=True)
        thread = await channel.create_thread(name=f"{emoji} {label} – {user.display_name}"[:MAX_NAME],
                                             type=discord.ChannelType.private_thread, invitable=False,
                                             reason=f"Ticket von {user}")
        await self.invite(thread, user, roles)
        await self.store.add(thread.id, guild.id, user.id, kind)
        await self.post_first_message(thread, user, roles, kind, text)
        await interaction.followup.send(f"Ticket erstellt: {thread.mention}", ephemeral=True)

    @staticmethod
    def cannot_open(channel: discord.TextChannel, roles: list[discord.Role]) -> str | None:
        if not roles:
            return "Noch keine Team-Rolle für Tickets eingerichtet (`/setup panel` → Tickets)."
        if not channel.permissions_for(channel.guild.me).create_private_threads:
            return "Mir fehlt das Recht „Private Threads erstellen“ in diesem Kanal."
        return None

    async def invite(self, thread: discord.Thread, user: discord.abc.User, roles: list[discord.Role]) -> None:
        """Ersteller und alle Team-Mitglieder (je einmal) in den Thread holen."""
        await thread.add_user(user)
        members = {m.id: m for role in roles for m in role.members}
        for member in members.values():
            try:
                await thread.add_user(member)
            except discord.HTTPException as e:
                self.log.warning("Ticket %s: Team-Mitglied %s nicht hinzugefügt: %r", thread.id, member.id, e)

    @staticmethod
    async def post_first_message(thread: discord.Thread, user: discord.abc.User, roles: list[discord.Role],
                                 kind: str, text: str) -> None:
        from .views import TicketCloseView

        emoji, label, _ = KINDS[kind]
        e = discord.Embed(title=f"{emoji} {label}", colour=discord.Colour.blurple(), description=text)
        e.set_author(name=user.display_name, icon_url=user.display_avatar.url)
        pings = " ".join(r.mention for r in roles)
        await thread.send(content=f"{user.mention} {pings}", embed=e, view=TicketCloseView(),
                          allowed_mentions=discord.AllowedMentions(users=True, roles=True))

    async def close(self, interaction: discord.Interaction) -> None:
        thread, user = interaction.channel, interaction.user
        row = await self.store.get(thread.id) if isinstance(thread, discord.Thread) else None
        if row is None or not isinstance(thread, discord.Thread) or not isinstance(user, discord.Member):
            await interaction.response.send_message("Das ist kein Ticket (mehr).", ephemeral=True)
            return
        if not self.may_close(user, row["user_id"]):
            await interaction.response.send_message("Nur das Team oder du selbst können dieses Ticket schließen.",
                                                    ephemeral=True)
            return
        await interaction.response.send_message("🔒 Wird geschlossen …")
        opener = thread.guild.get_member(row["user_id"])
        summary = discord.Embed(title=f"🎫 Ticket geschlossen: {thread.name}", colour=discord.Colour.dark_grey(),
                                description=f"Von {opener.mention if opener else row['user_id']}, "
                                            f"geschlossen von {user.mention}")
        await self.ctx.bus.emit(LOG, LogEntry(thread.guild, summary, await transcript(thread)))
        await self.store.close(thread.id)
        await thread.edit(archived=True, locked=True, reason=f"Geschlossen von {user}")

    def may_close(self, member: discord.Member, opener_id: int) -> bool:
        is_team = any(r in member.roles for r in self.team(member.guild))
        return is_team or member.id == opener_id or member.guild_permissions.manage_guild
