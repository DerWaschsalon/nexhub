"""Verifizierung im NexHub: eigene Seite (routes/hub/admin/bot/verifizierung) mit Stand und Regel-Text.
Eingerichtet wird weiter in Discord (/setup verifizierung), wegen Vorschau und Bestätigung."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from aiohttp import web

from bot.core.web import RouteTable, hub_guild, json_body
from bot.hubpages import Page

if TYPE_CHECKING:
    from . import Verification

PAGE_ORDER = 20


def verification_page() -> Page:
    return Page("verifizierung", "Verifizierung", "Server", order=PAGE_ORDER, custom=True)


def verification_routes(module: Verification, r: RouteTable) -> None:
    async def state(_request: web.Request) -> dict[str, Any]:
        guild = hub_guild(module.client)
        settings = module.settings.get(guild.id)
        channel = module.rules_channel(guild)
        role = guild.get_role(settings.verify_role or 0)
        message = await module.rules_message(guild)
        text = message.embeds[0].description if message and message.embeds else None
        return {"channel": channel.name if channel else None, "role": role.name if role else None,
                "panel": message is not None, "text": text}

    async def set_text(request: web.Request) -> None:
        text = str((await json_body(request)).get("text") or "")
        await module.set_text(hub_guild(module.client), text)

    r.control("GET", "/control/verification", state)
    r.control("PUT", "/control/verification/text", set_text)
