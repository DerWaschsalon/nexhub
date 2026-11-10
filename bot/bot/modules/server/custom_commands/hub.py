"""Eigene Befehle im NexHub: eigene Seite (routes/hub/admin/bot/befehle) mit Liste, anlegen, löschen."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from aiohttp import web

from bot.core.web import RouteTable, hub_guild, json_body
from bot.hubpages import ApiError, Page

if TYPE_CHECKING:
    from . import CustomCommands

PAGE_ORDER = 70
MAX_MESSAGE = 2000  # Länge einer Discord-Nachricht


def commands_page() -> Page:
    return Page("befehle", "Eigene Befehle", "Community", order=PAGE_ORDER, custom=True)


def command_routes(module: CustomCommands, r: RouteTable) -> None:
    async def listing(_request: web.Request) -> list[dict[str, Any]]:
        rows = await module.store.of_guild(hub_guild(module.client).id)
        return [{"name": row["name"], "response": row["response"]} for row in rows]

    async def put(request: web.Request) -> list[dict[str, Any]]:
        guild = hub_guild(module.client)
        response = str((await json_body(request)).get("response") or "").strip()
        if not response:
            raise ApiError(400, "Antwort fehlt")
        if len(response) > MAX_MESSAGE:
            raise ApiError(400, f"Höchstens {MAX_MESSAGE} Zeichen (Discord-Grenze)")
        await module.store.put(guild.id, request.match_info["name"], response)
        return await listing(request)

    async def delete(request: web.Request) -> None:
        await module.store.delete(hub_guild(module.client).id, request.match_info["name"])

    r.control("GET", "/control/commands", listing)
    r.control("PUT", "/control/commands/{name}", put)
    r.control("DELETE", "/control/commands/{name}", delete)
