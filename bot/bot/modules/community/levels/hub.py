"""Levelsystem im NexHub: eigene Seite für die Rollen-Belohnungen (routes/hub/admin/bot/level)."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from aiohttp import web

from bot.core.discord_checks import can_assign
from bot.core.web import RouteTable, hub_guild, json_body
from bot.hubpages import ApiError, Field, Page, action_values

if TYPE_CHECKING:
    from . import Levels

PAGE_ORDER = 20
MAX_LEVEL = 1000
ROLE = Field("role_id", "role", "Rolle", required=True)


def level_page() -> Page:
    return Page("level", "Levelsystem", "Community", order=PAGE_ORDER, custom=True)


def level_routes(module: Levels, r: RouteTable) -> None:
    async def rewards(_request: web.Request) -> list[dict[str, Any]]:
        guild = hub_guild(module.client)
        out = []
        for row in await module.store.rewards(guild.id):
            role = guild.get_role(row["role_id"])
            out.append({"level": row["level"], "role_id": str(row["role_id"]), "role": role.name if role else None})
        return out

    def level_of(request: web.Request) -> int:
        level = request.match_info["level"]
        if not level.isdigit() or not 1 <= int(level) <= MAX_LEVEL:
            raise ApiError(400, f"Level zwischen 1 und {MAX_LEVEL}")
        return int(level)

    async def reward_set(request: web.Request) -> list[dict[str, Any]]:
        guild = hub_guild(module.client)
        level = level_of(request)
        role = action_values(guild, (ROLE,), await json_body(request))["role_id"]
        if not can_assign(guild, role):
            raise ApiError(400, f"{role.name} kann der Bot nicht vergeben (muss unter seiner eigenen Rolle stehen)")
        await module.store.set_reward(guild.id, level, role.id)
        return await rewards(request)

    async def reward_delete(request: web.Request) -> None:
        await module.store.set_reward(hub_guild(module.client).id, level_of(request), None)

    r.control("GET", "/control/level-rewards", rewards)
    r.control("PUT", "/control/level-rewards/{level}", reward_set)
    r.control("DELETE", "/control/level-rewards/{level}", reward_delete)
