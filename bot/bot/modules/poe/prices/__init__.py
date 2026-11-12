"""Path-of-Exile-Preise: Preisalarme und Tagespost vom NexHub, /poe preis fragt den Hub.

Der Hub (hub/api/nexhub_api/poe_alerts.py) schickt Alarme an `/control/poe/alert` und die Tagespost an
`/control/poe/daily`; beides landet im eingestellten Kanal. Ohne Kanal antwortet der Bot trotzdem mit
200, weil der Hub dann nichts falsch gemacht hat. /poe preis holt Preise über HubClient (bot/core/hub.py).
"""

from __future__ import annotations

from typing import Any, ClassVar, TypeGuard

import discord
from aiohttp import web
from discord.ext import commands
from nexcore import ModuleInfo

from bot.core import BotContext, BotModule, GuildSettings, HubClient
from bot.core.web import RouteTable, json_body
from bot.hubpages import ApiError

from .embeds import alert_embed, daily_embed
from .settings import PoeSettings


def is_id(value: Any) -> TypeGuard[int]:
    # bool ist in Python auch ein int, als ID aber Unsinn
    return isinstance(value, int) and not isinstance(value, bool)


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
        guild_id = data.get("guild_id")
        if not is_id(guild_id) or self.client.get_guild(guild_id) is None:
            raise ApiError(400, "guild_id fehlt oder der Bot ist auf diesem Server nicht")
        channel_id = self.settings.get(guild_id).poe_channel
        if channel_id is None:
            return None
        channel = self.client.get_channel(channel_id)
        return channel if isinstance(channel, discord.TextChannel) else None

    async def alert(self, request: web.Request) -> dict[str, Any]:
        data = await json_body(request)
        channel = self.channel_for(data)
        if not is_id(data.get("discord_id")):
            raise ApiError(400, "discord_id fehlt")
        if channel is None:
            return {"posted": False}
        await channel.send(content=f"<@{data['discord_id']}>", embed=alert_embed(data),
                           allowed_mentions=discord.AllowedMentions(users=True))
        return {"posted": True}

    async def daily(self, request: web.Request) -> dict[str, Any]:
        data = await json_body(request)
        channel = self.channel_for(data)
        if channel is None:
            return {"posted": False}
        await channel.send(embed=daily_embed(data))
        return {"posted": True}
