"""Modul Dungeon-Runs: Bosskämpfe zu Runs zusammenfassen und als Bild nach Discord schicken."""
from __future__ import annotations

import asyncio
from typing import Any

from aiohttp import ClientSession, ClientTimeout, web
from nexcore import Context, ModuleInfo
from nexcore.errors import ApiError
from nexcore.settings import is_mask

from ..core.http import ok, read_object
from ..core.live import LiveHub
from ..runs import DungeonRuns, RunSettings, render_run
from ..state import State
from .base import WebModule

POST_TIMEOUT_S = 30
NO_RUN = "noch kein Dungeon-Run in der History"


class RunsModule(WebModule):
    info = ModuleInfo(
        "aion2.runs", "AION 2 · Dungeon-Runs", "games", "trophy",
        "Fasst Bosskämpfe zu Runs zusammen und postet nach jedem Run ein Bild mit dem Schaden pro "
        "Boss in einen Discord-Kanal.",
        requires=("aion2.dps",), tags=("AION 2", "Discord"),
    )
    ui_key = "runs"

    def __init__(self, ctx: Context, live: LiveHub, runs: DungeonRuns, state: State) -> None:
        super().__init__(ctx, live)
        self.runs = runs
        runs.listeners.append(self.changed)
        state.subscribe(self.on_state)

    def ui_info(self) -> dict[str, Any]:
        return self.runs.info()

    def on_state(self, diff: dict[str, Any]) -> None:
        if diff.get("dps"):
            self.runs.observe(diff["dps"])

    async def start(self) -> None:
        self.spawn(self.runs.watch)

    def status(self) -> dict[str, Any]:
        r = self.runs
        last = {"name": r.last.name, "end": r.last.end_ms, "kills": r.last.kills} if r.last else None
        return {"open_run": bool(r.tracker.run), "posting": bool(r.settings.enabled and r.settings.webhook),
                "last": last, "result": r.result}

    def routes(self, router: web.UrlDispatcher) -> None:
        router.add_get("/api/runs", self.api_get)
        router.add_put("/api/runs", self.api_put)
        router.add_get("/api/runs/preview.png", self.api_preview)
        router.add_post("/api/runs/test", self.api_test)

    async def api_get(self, request: web.Request) -> web.Response:
        return web.json_response(self.runs.info())

    async def api_put(self, request: web.Request) -> web.Response:
        data = await read_object(request)
        if "webhook" not in data or is_mask(data["webhook"]):  # Platzhalter aus info(): Webhook bleibt
            data["webhook"] = self.runs.settings.webhook
        self.runs.save(RunSettings.model_validate(data))
        await self.changed()
        return ok(**self.runs.info())

    async def latest_run(self) -> Any:
        run = await asyncio.to_thread(self.runs.latest_run)
        if not run:
            raise ApiError(404, NO_RUN)
        return run

    async def api_preview(self, request: web.Request) -> web.Response:
        """Letzter Run als Bild, so wie er nach Discord ginge."""
        image = await asyncio.to_thread(render_run, await self.latest_run())
        return web.Response(body=image, content_type="image/webp", headers={"Cache-Control": "no-store"})

    async def api_test(self, request: web.Request) -> web.Response:
        """Letzten Run jetzt nach Discord schicken (Knopf in der Web-UI)."""
        if not self.runs.settings.webhook:
            raise ApiError(400, "keine Webhook-URL eingetragen")
        run = await self.latest_run()
        async with ClientSession(timeout=ClientTimeout(total=POST_TIMEOUT_S)) as session:
            sent = await self.runs.post(session, run)
        await self.changed()
        if not sent:
            raise ApiError(502, self.runs.result)
        return ok(**self.runs.info())
