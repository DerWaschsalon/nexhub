"""/aufraeumen nachrichten, /aufraeumen bots, /aufraeumen bericht."""

from __future__ import annotations

import io
from datetime import timedelta
from typing import TYPE_CHECKING

import discord
from discord import app_commands
from discord.ext import commands

from bot.core import ModuleCog
from bot.core.confirm import Confirm
from bot.errors import UserError

from . import SCAN_LIMIT, MessageFilter, slow_count
from .report import server_report

if TYPE_CHECKING:
    from . import Cleanup

MAX_SELECT = 25  # Discord: höchstens 25 Einträge in einer Auswahl
MAX_EMBED = 4000
DELETES_PER_MINUTE = 60


def guild_of(interaction: discord.Interaction) -> discord.Guild:
    if interaction.guild is None:
        raise UserError("Das geht nur auf einem Server.")
    return interaction.guild


class BotSelect(discord.ui.Select["BotRemoveView"]):
    def __init__(self, bots: list[discord.Member]) -> None:
        options = [discord.SelectOption(label=str(b.display_name)[:100], value=str(b.id),
                                        description=f"Seit {b.joined_at:%d.%m.%Y}" if b.joined_at else None)
                   for b in bots]
        super().__init__(placeholder="Bots auswählen, die rausfliegen sollen", min_values=1, max_values=len(bots),
                         options=options)

    async def callback(self, interaction: discord.Interaction) -> None:
        assert self.view is not None
        self.view.selected = [int(v) for v in self.values]
        await interaction.response.defer()


class BotRemoveView(Confirm):
    def __init__(self, author_id: int, bots: list[discord.Member]) -> None:
        super().__init__(author_id, "Ausgewählte entfernen")
        self.selected: list[int] = []
        self.add_item(BotSelect(bots))

    async def accept(self, interaction: discord.Interaction) -> None:
        if not self.selected:
            await interaction.response.send_message("Erst Bots auswählen.", ephemeral=True)
            return
        await super().accept(interaction)


def can_kick(guild: discord.Guild, member: discord.Member) -> bool:
    return guild.me.guild_permissions.kick_members and member.top_role < guild.me.top_role


def bot_overview(bots: list[discord.Member], kickable: list[discord.Member]) -> discord.Embed:
    lines = []
    for b in bots:
        roles = ", ".join(r.name for r in b.roles if not r.is_default()) or "keine"
        since = f"{b.joined_at:%d.%m.%Y}" if b.joined_at else "?"
        lines.append(f"{'•' if b in kickable else '🔒'} **{discord.utils.escape_markdown(b.display_name)}** "
                     f"– seit {since} – Rollen: {roles}")
    e = discord.Embed(title=f"🤖 {len(bots)} Bots", description="\n".join(lines)[:MAX_EMBED],
                      colour=discord.Colour.blurple())
    if len(kickable) < len(bots):
        e.set_footer(text="🔒 = steht über meiner Rolle. Rolle des Bots in den Servereinstellungen über diese ziehen "
                          "oder den Bot von Hand entfernen.")
    return e


def preview(channel: discord.TextChannel, messages: list[discord.Message]) -> discord.Embed:
    e = discord.Embed(title=f"🧹 {len(messages)} Nachrichten in #{channel.name} löschen?", colour=discord.Colour.red())
    e.add_field(name="Zeitraum", value=f"{messages[-1].created_at:%d.%m.%Y} – {messages[0].created_at:%d.%m.%Y}")
    slow = slow_count(messages, discord.utils.utcnow())
    if slow:
        minutes = max(1, slow // DELETES_PER_MINUTE)
        e.add_field(name="Dauer", value=f"{slow} davon älter als 14 Tage, das dauert etwa {minutes} Min.")
    e.set_footer(text="Gelöschte Nachrichten lassen sich nicht wiederherstellen.")
    return e


@app_commands.guild_only()
@app_commands.default_permissions(manage_guild=True)
class CleanupCog(commands.GroupCog, ModuleCog, group_name="aufraeumen", group_description="Server aufräumen"):
    module: "Cleanup"

    @app_commands.command(name="nachrichten", description="Nachrichten in einem Kanal löschen (mit Vorschau)")
    @app_commands.describe(
        kanal="Welcher Kanal",
        aelter_als_tage="Nur Nachrichten, die älter sind als so viele Tage (0 = alle)",
        anzahl="Höchstens so viele löschen",
        von="Nur Nachrichten dieses Mitglieds oder Bots",
        nur_bots="Nur Nachrichten von Bots (z. B. alte Musikbot-Ausgaben)",
        angepinnte_behalten="Angepinnte Nachrichten nicht löschen",
    )
    async def messages(self, interaction: discord.Interaction, kanal: discord.TextChannel,
                       aelter_als_tage: app_commands.Range[int, 0, 3650] = 0,
                       anzahl: app_commands.Range[int, 1, SCAN_LIMIT] = 100, von: discord.User | None = None,
                       nur_bots: bool = False, angepinnte_behalten: bool = True) -> None:
        perms = kanal.permissions_for(kanal.guild.me)
        if not (perms.manage_messages and perms.read_message_history):
            raise UserError(f"In {kanal.mention} fehlen mir „Nachrichten verwalten“ und „Nachrichtenverlauf lesen“.")
        await interaction.response.defer(ephemeral=True, thinking=True)
        before = discord.utils.utcnow() - timedelta(days=aelter_als_tage) if aelter_als_tage else None
        wanted = MessageFilter(angepinnte_behalten, von.id if von else None, nur_bots)
        found = await self.module.find(kanal, before, anzahl, wanted.matches)
        if not found:
            await interaction.followup.send("Keine passenden Nachrichten gefunden.", ephemeral=True)
            return
        view = Confirm(interaction.user.id, f"{len(found)} löschen")
        await interaction.followup.send(embed=preview(kanal, found), view=view, ephemeral=True)
        await view.wait()
        if view.confirmed:
            count = await self.module.delete(kanal, found, before, f"Aufräumen durch {interaction.user}")
            await interaction.edit_original_response(content=f"✅ {count} Nachrichten gelöscht.")

    @app_commands.command(name="bots", description="Alte Bots anzeigen und entfernen")
    async def bots(self, interaction: discord.Interaction) -> None:
        guild = guild_of(interaction)
        bots = sorted((m for m in guild.members if m.bot and m != guild.me),
                      key=lambda m: m.joined_at or discord.utils.utcnow())
        if not bots:
            raise UserError("Außer mir sind keine Bots auf dem Server.")
        kickable = [b for b in bots if can_kick(guild, b)]
        if not kickable:
            await interaction.response.send_message(embed=bot_overview(bots, kickable), ephemeral=True)
            return
        view = BotRemoveView(interaction.user.id, kickable[:MAX_SELECT])
        await interaction.response.send_message(embed=bot_overview(bots, kickable), view=view, ephemeral=True)
        await view.wait()
        if view.confirmed:
            removed = await self.kick_all(guild, view.selected, f"Aufräumen durch {interaction.user}")
            await interaction.edit_original_response(
                content=f"✅ Entfernt: {', '.join(removed) or 'keiner'}.\nIhre automatischen Bot-Rollen verschwinden "
                        "dabei mit. Selbst angelegte Rollen für diese Bots bleiben, die siehst du in "
                        "`/aufraeumen bericht`.")

    async def kick_all(self, guild: discord.Guild, bot_ids: list[int], reason: str) -> list[str]:
        removed = []
        for bot_id in bot_ids:
            member = guild.get_member(bot_id)
            if member is None:
                continue
            try:
                await member.kick(reason=reason)
                removed.append(member.display_name)
            except discord.HTTPException as e:
                self.module.log.warning("Kick %s: %r", bot_id, e)
        return removed

    @app_commands.command(name="bericht", description="Übersicht über Kanäle, Aktivität und Rollen als Datei")
    async def report(self, interaction: discord.Interaction) -> None:
        now = discord.utils.utcnow()
        data = io.BytesIO(server_report(guild_of(interaction), now).encode())
        await interaction.response.send_message(
            "Hier der Bericht. ⚠️ markiert Kanäle ohne Nachricht seit 90 Tagen und leere Rollen.",
            file=discord.File(data, filename=f"server-bericht-{now:%Y-%m-%d}.md"), ephemeral=True)


