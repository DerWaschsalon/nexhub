"""Path-of-Exile-Preise: Preisalarme und Tagespost vom NexHub, /poe preis fragt den Hub.

Der Hub (hub/api/nexhub_api/poe_alerts.py) schickt Alarme an `/control/poe/alert` und die Tagespost an
`/control/poe/daily`; beides landet im eingestellten Kanal. Ohne Kanal antwortet der Bot trotzdem mit
200, weil der Hub dann nichts falsch gemacht hat. /poe preis holt Preise über HubClient (bot/core/hub.py).
"""

from __future__ import annotations

from typing import Any, ClassVar

import discord
from aiohttp import web
from discord.ext import commands
from nexcore import ModuleInfo

from bot.core import BotContext, BotModule, GuildSettings, HubClient
from bot.core.web import RouteTable, guild_id_from, is_id, json_body, require_fields
from bot.hubpages import ApiError

from .embeds import alert_embed, daily_embed
from .settings import PoeSettings

# Felder einer Preisänderung (`Move` in hub/api/nexhub_api/poe_alerts.py)
MOVE_FIELDS = ("key", "name", "icon", "old", "new", "unit", "change", "url")
SIDES = ("up", "down")


class PoePrices(BotModule):
    info: ClassVar[ModuleInfo] = ModuleInfo(
        id="poe.prices", name="Path of Exile Preise", category="Path of Exile", icon="mdi-cash",
        summary="Preisalarme aus der NexHub-Merkliste, Tagespost mit Gewinnern und Verlierern, /poe preis.",
    )
    Settings = PoeSettings

    def __init__(self, ctx: BotContext) -> None:
        super().__init__(ctx)
        self.settings = GuildSettings(ctx.db, PoeSettings)
        self.hub = HubClient.from_env()

    def cog(self) -> commands.Cog:
        from .commands import PoeCog

        return PoeCog(self)

    def routes(self, r: RouteTable) -> None:
        r.control("POST", "/control/poe/alert", self.alert)
        r.control("POST", "/control/poe/daily", self.daily)

    async def shutdown(self) -> None:
        if self.hub is not None:
            await self.hub.close()
        await super().shutdown()

    def channel_for(self, data: dict[str, Any]) -> discord.TextChannel | None:
        """Kanal für die Posts auf dem Server aus `guild_id`, oder None, wenn keiner eingestellt ist."""
        guild_id = guild_id_from(self.client, data)
        channel_id = self.settings.get(guild_id).poe_channel
        if channel_id is None:
            return None
        channel = self.client.get_channel(channel_id)
        if not isinstance(channel, discord.TextChannel):
            self.log.warning("Server %s: Kanal %s für PoE-Preise fehlt oder ist kein Textkanal", guild_id, channel_id)
            return None
        return channel

    async def alert(self, request: web.Request) -> dict[str, Any]:
        data = await json_body(request)
        channel = self.channel_for(data)
        if not is_id(data.get("discord_id")):
            raise ApiError(400, "discord_id fehlt")
        require_fields(data, ("game", "league", *MOVE_FIELDS))
        if channel is None:
            return {"posted": False}
        await channel.send(content=f"<@{data['discord_id']}>", embed=alert_embed(data),
                           allowed_mentions=discord.AllowedMentions(users=True))
        return {"posted": True}

    async def daily(self, request: web.Request) -> dict[str, Any]:
        data = await json_body(request)
        channel = self.channel_for(data)
        require_fields(data, ("game", "league", *SIDES))
        for side in SIDES:
            if not isinstance(data[side], list):
                raise ApiError(400, f"{side}: Liste erwartet")
            for move in data[side]:
                require_fields(move, MOVE_FIELDS)
        if channel is None:
            return {"posted": False}
        await channel.send(embed=daily_embed(data))
        return {"posted": True}
