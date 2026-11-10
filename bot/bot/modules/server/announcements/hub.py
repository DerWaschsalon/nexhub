"""Ankündigungen im NexHub: eigene Seite (routes/hub/admin/bot/ankuendigungen) mit Liste, anlegen, löschen."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from aiohttp import web

from bot.core.web import RouteTable, hub_guild, json_body
from bot.hubpages import ApiError, Field, Page, action_values

if TYPE_CHECKING:
    from . import Announcements

PAGE_ORDER = 60
MAX_MESSAGE = 2000  # Länge einer Discord-Nachricht
MIN_INTERVAL_MIN = 5
CHANNEL = Field("channel_id", "channel", "Kanal", required=True)


def announcements_page() -> Page:
    return Page("ankuendigungen", "Ankündigungen", "Community", order=PAGE_ORDER, custom=True)


def announcement_routes(module: Announcements, r: RouteTable) -> None:
    async def listing(_request: web.Request) -> list[dict[str, Any]]:
        guild = hub_guild(module.client)
        out = []
        for row in await module.store.of_guild(guild.id):
            ch = guild.get_channel(row["channel_id"])
            out.append({"id": row["id"], "channel_id": str(row["channel_id"]), "channel": ch.name if ch else None,
                        "text": row["text"], "interval_minutes": row["interval_minutes"],
                        "next_run": row["next_run"]})
        return out

    async def add(request: web.Request) -> list[dict[str, Any]]:
        guild = hub_guild(module.client)
        data = await json_body(request)
        text = str(data.get("text") or "").strip()
        interval = data.get("interval_minutes")
        if not data.get("channel_id") or not text:
            raise ApiError(400, "Kanal und Text angeben")
        channel = action_values(guild, (CHANNEL,), data)["channel_id"]
        if len(text) > MAX_MESSAGE:
            raise ApiError(400, f"Höchstens {MAX_MESSAGE} Zeichen (Discord-Grenze)")
        if isinstance(interval, bool) or not isinstance(interval, int) or interval < MIN_INTERVAL_MIN:
            raise ApiError(400, f"Intervall mindestens {MIN_INTERVAL_MIN} Minuten")
        await module.store.add(guild.id, channel.id, text, interval)
        return await listing(request)

    async def delete(request: web.Request) -> None:
        ann_id = request.match_info["id"]
        if not ann_id.isdigit():
            raise ApiError(404, "Ankündigung gibt es nicht")
        await module.store.delete(hub_guild(module.client).id, int(ann_id))

    r.control("GET", "/control/announcements", listing)
    r.control("POST", "/control/announcements", add)
    r.control("DELETE", "/control/announcements/{id}", delete)
