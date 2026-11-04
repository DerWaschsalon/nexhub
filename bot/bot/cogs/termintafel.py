"""Termin-Tafel für AION 2: eine Nachricht im eingestellten Kanal, die sich jede Minute selbst
aktualisiert (Riss, Shugo-Fest, Beritra-Luftangriff, Wächterin Kaira, Resets).

Die Zeiten stehen als Discord-Zeitstempel in der Nachricht, deshalb sieht jeder sie in seiner eigenen
Zeitzone, ohne Einstellung. 5 Minuten vor einem Ereignis (nicht vor den Resets) kommt ein Ping an die
eingestellte Rolle, der sich nach Beginn selbst löscht. Die Termine stehen genau einmal im Monorepo, in
proto/nexproto/termine.py (dieselben wie im Radar des NexBoards).
"""

from __future__ import annotations

import logging
import sys
import time
from pathlib import Path

import discord
from discord.ext import commands, tasks

try:
    import termine  # im Image: von bot/Dockerfile aus proto/nexproto/termine.py kopiert
except ImportError:  # im Repo (Tests, Entwicklung): direkt aus proto
    sys.path.append(str(Path(__file__).resolve().parents[3] / "proto" / "nexproto"))
    import termine

log = logging.getLogger(__name__)

PING_VORHER_S = 5 * 60
OHNE_PING = ("Tages-Reset", "Wochen-Reset")


def tafel(jetzt: float) -> discord.Embed:
    """Die Nachricht der Tafel: je Termin der nächste Beginn, oder „läuft bis …“, solange er offen ist."""
    zeilen = []
    for name, beginn, offen_bis in termine.alle(jetzt):
        if offen_bis:
            zeilen.append(f"🟢 **{name}** läuft, bis <t:{int(offen_bis)}:t> (<t:{int(offen_bis)}:R>)")
        else:
            zeilen.append(f"**{name}** <t:{int(beginn)}:t> (<t:{int(beginn)}:R>)")
    embed = discord.Embed(title="AION 2 · Termine", description="\n".join(zeilen), color=0x7DD8D8)
    embed.set_footer(text="Zeiten in deiner Zeitzone · aktualisiert sich jede Minute · Riss bestätigt, Rest geschätzt")
    return embed


def faellige_pings(jetzt: float, gemeldet: set[tuple[str, int]]) -> list[tuple[str, int]]:
    """Ereignisse, die in den nächsten 5 Minuten beginnen und noch nicht gemeldet sind: (Name, Beginn)."""
    faellig = []
    for name, beginn, offen_bis in termine.alle(jetzt):
        key = (name, int(beginn))
        if name not in OHNE_PING and not offen_bis and 0 < beginn - jetzt <= PING_VORHER_S and key not in gemeldet:
            faellig.append(key)
    return faellig


class Termintafel(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.db = bot.db
        self.gemeldet: dict[int, set[tuple[str, int]]] = {}  # Server → schon gepingte Termine
        self.aktualisieren.start()

    def cog_unload(self):
        self.aktualisieren.cancel()

    @tasks.loop(minutes=1)
    async def aktualisieren(self):
        jetzt = time.time()
        for guild_id in self.db.guilds_with("termine_channel"):
            channel = self.bot.get_channel(self.db.get_int(guild_id, "termine_channel"))
            if not isinstance(channel, discord.TextChannel):
                continue
            try:
                await self._tafel(guild_id, channel, jetzt)
                await self._pings(guild_id, channel, jetzt)
            except discord.HTTPException as ex:
                log.warning("Termin-Tafel %s: %r", guild_id, ex)

    @aktualisieren.before_loop
    async def vor_dem_start(self):
        await self.bot.wait_until_ready()

    async def _tafel(self, guild_id: int, channel: discord.TextChannel, jetzt: float) -> None:
        """Eigene Nachricht bearbeiten; fehlt sie (gelöscht, Kanal gewechselt), eine neue schicken."""
        message_id = self.db.get_int(guild_id, "termine_message")
        if message_id and self.db.get_int(guild_id, "termine_message_channel") == channel.id:
            try:
                await channel.get_partial_message(message_id).edit(embed=tafel(jetzt))
                return
            except discord.NotFound:
                pass
        message = await channel.send(embed=tafel(jetzt))
        await self.db.set(guild_id, "termine_message", message.id)
        await self.db.set(guild_id, "termine_message_channel", channel.id)

    async def _pings(self, guild_id: int, channel: discord.TextChannel, jetzt: float) -> None:
        role_id = self.db.get_int(guild_id, "termine_role")
        role = channel.guild.get_role(role_id) if role_id else None
        if not role:
            return
        gemeldet = self.gemeldet.setdefault(guild_id, set())
        for name, beginn in faellige_pings(jetzt, gemeldet):
            gemeldet.add((name, beginn))
            await channel.send(f"{role.mention} **{name}** beginnt <t:{beginn}:R>.",
                               allowed_mentions=discord.AllowedMentions(roles=True),
                               delete_after=max(60, beginn - jetzt + 60))
        # alte Einträge vergessen, damit die Menge nicht wächst
        gemeldet.intersection_update({k for k in gemeldet if k[1] > jetzt - 3600})


async def setup(bot):
    await bot.add_cog(Termintafel(bot))
