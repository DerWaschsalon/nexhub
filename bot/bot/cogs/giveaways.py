"""Giveaways: Embed mit „🎉 Teilnehmen“-Button (Klick an/abmelden), automatische Auslosung nach
Ablauf, `/giveaway-reroll` für neue Gewinner. Der Button-`custom_id` trägt die Nachrichten-ID
selbst, deshalb reicht `register_persistent_views` (einmal pro aktivem Giveaway beim Start), um
nach einem Neustart weiter klickbar zu sein — ganz ohne eigenen Zustand im View.
"""

from __future__ import annotations

import logging
import random
import time
from datetime import datetime, timezone

import discord
from discord import app_commands
from discord.ext import commands, tasks

from .reminders import TZ, parse_when
from ..errors import UserError
from ..hubpages import Action, Column, Field, Page, Table, channel_label, user_label

log = logging.getLogger(__name__)


def build_giveaway_embed(
    prize: str, winner_count: int, ends_at: float, host_id: int | None, *,
    ended: bool = False, winner_ids: list[int] | None = None,
) -> discord.Embed:
    if ended:
        e = discord.Embed(title="🎉 Giveaway beendet", description=f"**{prize}**", colour=discord.Colour.dark_grey())
        e.add_field(name="Gewinner", value=", ".join(f"<@{w}>" for w in winner_ids) if winner_ids else "Niemand hat teilgenommen")
    else:
        e = discord.Embed(title="🎉 Giveaway", description=f"**{prize}**", colour=discord.Colour.gold())
        ends_dt = datetime.fromtimestamp(ends_at, tz=timezone.utc)
        e.add_field(name="Endet", value=discord.utils.format_dt(ends_dt, "R"))
        e.add_field(name="Gewinner-Anzahl", value=str(winner_count))
        if host_id:
            e.add_field(name="Gestartet von", value=f"<@{host_id}>")
    return e


class GiveawayJoinButton(discord.ui.Button):
    def __init__(self, giveaway_id: int):
        super().__init__(label="🎉 Teilnehmen", style=discord.ButtonStyle.success,
                         custom_id=f"giveaway:join:{giveaway_id}")
        self.giveaway_id = giveaway_id

    async def callback(self, interaction: discord.Interaction):
        cog = interaction.client.get_cog("Giveaways")
        await cog.toggle_entry(interaction, self.giveaway_id)


class GiveawayView(discord.ui.View):
    def __init__(self, giveaway_id: int):
        super().__init__(timeout=None)
        self.add_item(GiveawayJoinButton(giveaway_id))


class Giveaways(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.db = bot.db
        self.check_due.start()

    def cog_unload(self):
        self.check_due.cancel()

    async def register_persistent_views(self) -> None:
        rows = await self.db.fetchall("SELECT message_id FROM giveaways WHERE ended=0")
        for row in rows:
            self.bot.add_view(GiveawayView(row["message_id"]), message_id=row["message_id"])

    @app_commands.command(name="giveaway-erstellen", description="Giveaway mit Teilnahme-Button starten")
    @app_commands.describe(
        kanal="Kanal für das Giveaway", preis="Was es zu gewinnen gibt", dauer="z. B. 2h, 30m, 1d2h",
        gewinner="Wie viele Gewinner ausgelost werden (Standard 1)",
    )
    @app_commands.guild_only()
    @app_commands.default_permissions(manage_guild=True)
    async def create(
        self, interaction: discord.Interaction, kanal: discord.TextChannel, preis: str, dauer: str,
        gewinner: app_commands.Range[int, 1, 20] = 1,
    ):
        await self.start(kanal, preis, dauer, gewinner, interaction.user.id)
        await interaction.response.send_message(f"Giveaway gestartet in {kanal.mention}.", ephemeral=True)

    async def start(self, channel: discord.TextChannel, prize: str, duration: str, winners: int, host_id: int) -> None:
        """Giveaway posten und eintragen (Befehl und Hub)."""
        if not channel.permissions_for(channel.guild.me).send_messages:
            raise UserError(f"Ich darf in #{channel.name} nicht schreiben.")
        ends_at = parse_when(duration, datetime.now(TZ)).timestamp()
        message = await channel.send(embed=build_giveaway_embed(prize, winners, ends_at, host_id))
        view = GiveawayView(message.id)
        await message.edit(view=view)
        self.bot.add_view(view, message_id=message.id)
        await self.db.execute(
            "INSERT INTO giveaways (message_id, guild_id, channel_id, host_id, prize, winners, ends, ended) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, 0)",
            (message.id, channel.guild.id, channel.id, host_id, prize, winners, ends_at),
        )

    async def toggle_entry(self, interaction: discord.Interaction, giveaway_id: int) -> None:
        row = await self.db.fetchone("SELECT ended FROM giveaways WHERE message_id=?", (giveaway_id,))
        if not row or row["ended"]:
            return await interaction.response.send_message("Dieses Giveaway ist schon vorbei.", ephemeral=True)
        existing = await self.db.fetchone(
            "SELECT 1 FROM giveaway_entries WHERE message_id=? AND user_id=?", (giveaway_id, interaction.user.id)
        )
        if existing:
            await self.db.execute(
                "DELETE FROM giveaway_entries WHERE message_id=? AND user_id=?", (giveaway_id, interaction.user.id)
            )
            return await interaction.response.send_message("Du nimmst nicht mehr teil.", ephemeral=True)
        await self.db.execute(
            "INSERT INTO giveaway_entries (message_id, user_id) VALUES (?, ?)", (giveaway_id, interaction.user.id)
        )
        await interaction.response.send_message("Du nimmst jetzt teil! 🎉", ephemeral=True)

    async def pick_winners(self, giveaway_id: int, count: int) -> list[int]:
        rows = await self.db.fetchall("SELECT user_id FROM giveaway_entries WHERE message_id=?", (giveaway_id,))
        ids = [r["user_id"] for r in rows]
        random.shuffle(ids)
        return ids[:count]

    @tasks.loop(minutes=1)
    async def check_due(self):
        now = time.time()
        rows = await self.db.fetchall("SELECT * FROM giveaways WHERE ended=0 AND ends<=?", (now,))
        for row in rows:
            await self._finish(row)

    @check_due.before_loop
    async def before_check_due(self):
        await self.bot.wait_until_ready()
        await self.register_persistent_views()

    async def _finish(self, row) -> None:
        await self.db.execute("UPDATE giveaways SET ended=1 WHERE message_id=?", (row["message_id"],))
        winners = await self.pick_winners(row["message_id"], row["winners"])
        channel = self.bot.get_channel(row["channel_id"])
        if not channel:
            return
        try:
            message = await channel.fetch_message(row["message_id"])
            await message.edit(
                embed=build_giveaway_embed(row["prize"], row["winners"], row["ends"], None, ended=True, winner_ids=winners),
                view=None,
            )
        except discord.HTTPException as ex:
            log.warning("Giveaway-Nachricht #%s bearbeiten: %r", row["message_id"], ex)
        text = (f"🎉 Gewinner von **{row['prize']}**: {', '.join(f'<@{w}>' for w in winners)}" if winners
               else f"😢 Niemand hat bei **{row['prize']}** mitgemacht.")
        try:
            await channel.send(text)
        except discord.HTTPException as ex:
            log.warning("Giveaway-Ergebnis #%s posten: %r", row["message_id"], ex)

    @app_commands.command(name="giveaway-reroll", description="Neue Gewinner für ein beendetes Giveaway auslosen")
    @app_commands.describe(giveaway_nachricht_id="Nachrichten-ID des Giveaway-Posts")
    @app_commands.guild_only()
    @app_commands.default_permissions(manage_guild=True)
    async def reroll(self, interaction: discord.Interaction, giveaway_nachricht_id: str):
        if not giveaway_nachricht_id.isdigit():
            raise UserError("Das ist keine gültige Nachrichten-ID.")
        message_id = int(giveaway_nachricht_id)
        row = await self.db.fetchone(
            "SELECT * FROM giveaways WHERE message_id=? AND guild_id=?", (message_id, interaction.guild_id)
        )
        if not row:
            raise UserError("Kein Giveaway mit dieser Nachrichten-ID auf diesem Server gefunden.")
        await interaction.response.send_message(await self.redraw(row), ephemeral=True)

    async def redraw(self, row) -> str:
        if not row["ended"]:
            raise UserError("Dieses Giveaway läuft noch.")
        winners = await self.pick_winners(row["message_id"], row["winners"])
        if not winners:
            return "Es gibt keine Teilnehmer zum Auslosen."
        channel = self.bot.get_channel(row["channel_id"])
        text = f"🔁 Neu ausgelost für **{row['prize']}**: {', '.join(f'<@{w}>' for w in winners)}"
        if channel:
            await channel.send(text)
        return "Neu ausgelost."

    # ---- NexHub ----

    def hub_pages(self) -> list[Page]:
        return [Page("giveaways", "Giveaways", "Community", (
            Table("giveaways", "Giveaways", (
                Column("prize", "Preis"), Column("channel", "Kanal"), Column("ends", "Endet", "time"),
                Column("entries", "Teilnehmer", "num"), Column("winners", "Gewinner", "num"),
                Column("state", "Status", "badge"),
            ), self._hub_rows,
                create=Action("create", "Neues Giveaway", self._hub_create, (
                    Field("channel", "channel", "Kanal", required=True),
                    Field("prize", "text", "Preis", required=True),
                    Field("duration", "text", "Dauer", hint="z. B. 2h, 30m, 1d2h oder 24.12. 18:00", required=True),
                    Field("winners", "int", "Anzahl Gewinner", default=1, min=1, max=20),
                ), submit="Giveaway starten"),
                actions=(
                    Action("end", "Jetzt auslosen", self._hub_end, confirm="Giveaway jetzt beenden und auslosen?", when="active"),
                    Action("reroll", "Neu auslosen", self._hub_reroll, confirm="Neue Gewinner auslosen?", when="ended"),
                    Action("delete", "Löschen", self._hub_delete, confirm="Giveaway samt Post löschen?", danger=True),
                ), empty="Noch keine Giveaways."),
        ), "Mit Teilnahme-Knopf in Discord, ausgelost wird automatisch zur Endzeit.", order=40)]

    async def _hub_rows(self, ctx) -> list[dict]:
        rows = await self.db.fetchall(
            "SELECT g.*, (SELECT COUNT(*) FROM giveaway_entries e WHERE e.message_id=g.message_id) AS n "
            "FROM giveaways g WHERE guild_id=? ORDER BY ended, ends DESC LIMIT 100", (ctx.guild.id,),
        )
        return [{"id": str(r["message_id"]), "prize": r["prize"], "channel": channel_label(ctx.guild, r["channel_id"]),
                 "ends": r["ends"], "entries": r["n"], "winners": r["winners"],
                 "state": "beendet" if r["ended"] else "läuft", "state_tone": "" if r["ended"] else "ok",
                 "host": user_label(ctx.guild, r["host_id"]), "active": not r["ended"], "ended": bool(r["ended"])}
                for r in rows]

    async def _hub_row(self, ctx, item):
        row = await self.db.fetchone("SELECT * FROM giveaways WHERE message_id=? AND guild_id=?",
                                     (int(item or 0), ctx.guild.id))
        if not row:
            raise UserError("Das Giveaway gibt es nicht mehr.")
        return row

    async def _hub_create(self, ctx, v, _item):
        await self.start(v["channel"], v["prize"], v["duration"], v["winners"], ctx.who_id or ctx.guild.me.id)
        return f"Giveaway gestartet in #{v['channel'].name}."

    async def _hub_end(self, ctx, _v, item):
        row = await self._hub_row(ctx, item)
        if row["ended"]:
            raise UserError("Das Giveaway ist schon vorbei.")
        await self._finish(row)
        return "Ausgelost."

    async def _hub_reroll(self, ctx, _v, item):
        return await self.redraw(await self._hub_row(ctx, item))

    async def _hub_delete(self, ctx, _v, item):
        row = await self._hub_row(ctx, item)
        channel = self.bot.get_channel(row["channel_id"])
        if channel:
            try:
                await (await channel.fetch_message(row["message_id"])).delete()
            except discord.HTTPException:
                pass
        await self.db.execute("DELETE FROM giveaway_entries WHERE message_id=?", (row["message_id"],))
        await self.db.execute("DELETE FROM giveaways WHERE message_id=?", (row["message_id"],))
        return "Gelöscht."


async def setup(bot):
    await bot.add_cog(Giveaways(bot))
