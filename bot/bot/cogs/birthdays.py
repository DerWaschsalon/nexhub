"""Geburtstage: Mitglieder tragen ihren Geburtstag ein, der Bot gratuliert täglich um 9 Uhr
(Europe/Berlin) im eingerichteten Kanal. `birthday_last_run` (Datum als Text) verhindert, dass
der Loop innerhalb derselben Stunde mehrfach gratuliert.
"""

from __future__ import annotations

import logging
from datetime import datetime
from zoneinfo import ZoneInfo

import discord
from discord import app_commands
from discord.ext import commands, tasks

from ..errors import UserError
from ..hubpages import Action, Column, Field, Page, Table, user_label

log = logging.getLogger(__name__)
TZ = ZoneInfo("Europe/Berlin")

DAYS_IN_MONTH = {1: 31, 2: 29, 3: 31, 4: 30, 5: 31, 6: 30, 7: 31, 8: 31, 9: 30, 10: 31, 11: 30, 12: 31}


class Birthdays(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.db = bot.db
        self.check.start()

    def cog_unload(self):
        self.check.cancel()

    @app_commands.command(name="geburtstag-setzen", description="Deinen Geburtstag eintragen (für die tägliche Gratulation)")
    @app_commands.describe(tag="Tag (1-31)", monat="Monat (1-12)")
    @app_commands.guild_only()
    async def set_birthday(
        self, interaction: discord.Interaction, tag: app_commands.Range[int, 1, 31], monat: app_commands.Range[int, 1, 12]
    ):
        if tag > DAYS_IN_MONTH[monat]:
            raise UserError(f"Monat {monat} hat höchstens {DAYS_IN_MONTH[monat]} Tage.")
        await self.db.execute(
            "INSERT INTO birthdays (guild_id, user_id, day, month) VALUES (?, ?, ?, ?) "
            "ON CONFLICT(guild_id, user_id) DO UPDATE SET day=excluded.day, month=excluded.month",
            (interaction.guild_id, interaction.user.id, tag, monat),
        )
        await interaction.response.send_message(f"Geburtstag gespeichert: {tag}.{monat}.", ephemeral=True)

    @app_commands.command(name="geburtstag-loeschen", description="Deinen eingetragenen Geburtstag wieder löschen")
    @app_commands.guild_only()
    async def delete_birthday(self, interaction: discord.Interaction):
        await self.db.execute(
            "DELETE FROM birthdays WHERE guild_id=? AND user_id=?", (interaction.guild_id, interaction.user.id)
        )
        await interaction.response.send_message("Geburtstag gelöscht.", ephemeral=True)

    @app_commands.command(name="geburtstag", description="Eingetragenen Geburtstag eines Mitglieds anzeigen (leer = dein eigener)")
    @app_commands.guild_only()
    async def show_birthday(self, interaction: discord.Interaction, nutzer: discord.Member | None = None):
        member = nutzer or interaction.user
        row = await self.db.fetchone(
            "SELECT day, month FROM birthdays WHERE guild_id=? AND user_id=?", (interaction.guild_id, member.id)
        )
        if not row:
            return await interaction.response.send_message(
                f"{member.mention} hat keinen Geburtstag eingetragen.", ephemeral=True
            )
        await interaction.response.send_message(f"{member.mention}: {row['day']}.{row['month']}.", ephemeral=True)

    @tasks.loop(minutes=30)
    async def check(self):
        now = datetime.now(TZ)
        if now.hour != 9:
            return
        today = now.strftime("%Y-%m-%d")
        for guild_id in self.db.guilds_with("birthday_channel"):
            if self.db.get(guild_id, "birthday_last_run") == today:
                continue
            await self._announce(guild_id, now)
            await self.db.set(guild_id, "birthday_last_run", today)

    @check.before_loop
    async def before_check(self):
        await self.bot.wait_until_ready()

    async def _announce(self, guild_id: int, now: datetime) -> None:
        guild = self.bot.get_guild(guild_id)
        channel_id = self.db.get_int(guild_id, "birthday_channel")
        channel = guild.get_channel(channel_id) if guild and channel_id else None
        if not channel:
            return
        rows = await self.db.fetchall(
            "SELECT user_id FROM birthdays WHERE guild_id=? AND day=? AND month=?", (guild_id, now.day, now.month)
        )
        for row in rows:
            member = guild.get_member(row["user_id"])
            if not member:
                continue
            try:
                await channel.send(f"🎉 Alles Gute zum Geburtstag, {member.mention}! 🎂")
            except discord.HTTPException as ex:
                log.warning("Geburtstagsgruß %s: %r", guild_id, ex)

    # ---- NexHub ----

    def hub_pages(self) -> list[Page]:
        return [Page("geburtstage", "Geburtstage", "Community", (
            Table("birthdays", "Geburtstage", (Column("user", "Mitglied"), Column("date", "Datum")), self._hub_rows,
                  create=Action("set", "Eintragen", self._hub_set, (
                      Field("member", "member", "Mitglied", required=True),
                      Field("day", "int", "Tag", default=1, min=1, max=31),
                      Field("month", "int", "Monat", default=1, min=1, max=12),
                  ), submit="Speichern"),
                  actions=(Action("delete", "Löschen", self._hub_delete, confirm="Geburtstag löschen?", danger=True),),
                  empty="Noch keine Geburtstage eingetragen."),
        ), "Gratuliert wird um 9 Uhr im Kanal aus „Community“. Mitglieder tragen sich mit /geburtstag-setzen ein.",
            order=50)]

    async def _hub_rows(self, ctx) -> list[dict]:
        rows = await self.db.fetchall("SELECT * FROM birthdays WHERE guild_id=? ORDER BY month, day", (ctx.guild.id,))
        return [{"id": str(r["user_id"]), "user": user_label(ctx.guild, r["user_id"]),
                 "date": f"{r['day']:02}.{r['month']:02}."} for r in rows]

    async def _hub_set(self, ctx, v, _item):
        try:
            datetime(2024, v["month"], v["day"])  # Schaltjahr: 29.2. ist erlaubt
        except ValueError:
            raise UserError("Dieses Datum gibt es nicht.")
        await self.db.execute(
            "INSERT INTO birthdays (guild_id, user_id, day, month) VALUES (?, ?, ?, ?) "
            "ON CONFLICT(guild_id, user_id) DO UPDATE SET day=excluded.day, month=excluded.month",
            (ctx.guild.id, v["member"].id, v["day"], v["month"]))
        return f"Geburtstag von {v['member'].display_name} eingetragen."

    async def _hub_delete(self, ctx, _v, item):
        await self.db.execute("DELETE FROM birthdays WHERE guild_id=? AND user_id=?", (ctx.guild.id, int(item or 0)))
        return "Gelöscht."

async def setup(bot):
    await bot.add_cog(Birthdays(bot))
