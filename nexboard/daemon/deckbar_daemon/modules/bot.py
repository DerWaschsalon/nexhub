"""Modul Discord-Bot: Gruppen-DPS und Run-Ergebnisse an einen Discord-Bot schicken."""
from __future__ import annotations

import asyncio
from typing import Any

from aiohttp import web
from nexcore import Context, ModuleInfo
from nexcore.errors import ApiError

from ..bot import DiscordBot
from ..core.http import ok, read_object
from ..core.live import LiveHub
from ..runs import DungeonRuns
from .base import WebModule


class BotModule(WebModule):
    info = ModuleInfo(
        "discord.bot", "Discord-Bot", "community", "robot",
        "Schickt Gruppen-DPS nach Bosskämpfen und Run-Ergebnisse an einen Discord-Bot "
        "(z. B. TheWashBot), der Meldungen mehrerer Spieler zusammenführt.",
        requires=("aion2.dps",), tags=("Discord", "Gruppe"),
    )
    ui_key = "bot"

    def __init__(self, ctx: Context, live: LiveHub, bot: DiscordBot, runs: DungeonRuns) -> None:
        super().__init__(ctx, live)
        self.bot = bot
        self.runs = runs
        bot.listeners.append(self.changed)

    def ui_info(self) -> dict[str, Any]:
        return self.bot.info()

    async def start(self) -> None:
        self.bot.enabled = True

    async def stop(self) -> None:
        self.bot.enabled = False
        await self.bot.close()

    def status(self) -> dict[str, Any]:
        s = self.bot.settings
        return {"dps": bool(s.dps_enabled and s.dps_url), "runs": bool(s.runs_enabled and s.runs_url and s.runs_token),
                "result": self.bot.result}

    def routes(self, router: web.UrlDispatcher) -> None:
        router.add_get("/api/bot", self.api_get)
        router.add_put("/api/bot", self.api_put)
        router.add_post("/api/bot/test/{kind:dps|runs}", self.api_test)

    async def api_get(self, request: web.Request) -> web.Response:
        return web.json_response(self.bot.info())

    async def api_put(self, request: web.Request) -> web.Response:
        self.bot.update(await read_object(request))
        await self.changed()
        return ok(**self.bot.info())

    async def api_test(self, request: web.Request) -> web.Response:
        self.require_active()
        if request.match_info["kind"] == "dps":
            sent, text = await self.bot.test_fight()
        else:
            sent, text = await self.bot.test_run(await asyncio.to_thread(self.runs.latest_run))
        if not sent:
            # Antwort des Bots oder Netzfehler (mit Doppelpunkt) = 502, sonst fehlt etwas in den Einstellungen
            raise ApiError(502 if "antwortet" in text or ":" in text else 400, text)
        return ok(text=text, **self.bot.info())
