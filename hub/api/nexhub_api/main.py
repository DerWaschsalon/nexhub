"""FastAPI-Anwendung: API unter /api, alles andere ist die statische Web-Oberfläche."""
from __future__ import annotations

import asyncio
import logging
from contextlib import asynccontextmanager

import httpx
from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import FileResponse, JSONResponse
from sqlalchemy import text
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from .aion2 import NC
from .armory import Armory
from .bis_collector import BisCollector
from .census import Census
from .characters import Fetcher
from .config import Settings
from .deps import DB, SESSION_COOKIE
from .poe_ninja import Game, PoeNinja
from .poe_prices import PoePrices
from .routes import ROUTERS

log = logging.getLogger(__name__)

SAFE_METHODS = {"GET", "HEAD", "OPTIONS"}


async def after_poe_refresh(game: Game, league: str) -> None:
    """Nach jedem Preisabruf eines Spiels; Alarme und Tagespost kommen hier später dazu."""


def create_app(settings: Settings | None = None, http: httpx.AsyncClient | None = None) -> FastAPI:
    settings = settings or Settings()

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        engine = create_async_engine(settings.database_url, pool_pre_ping=True)
        app.state.sessionmaker = async_sessionmaker(engine, expire_on_commit=False)
        app.state.http = http or httpx.AsyncClient(timeout=10)
        if not settings.discord_configured:
            log.warning("DISCORD_CLIENT_ID/DISCORD_CLIENT_SECRET fehlen – Login ist aus")
        app.state.characters, app.state.armory, tasks = None, None, []
        if settings.hub_aion2_enabled:
            nc = NC(app.state.http, settings.hub_aion2_pause)
            app.state.characters = Fetcher(app.state.sessionmaker, nc)
            app.state.armory = Armory(app.state.sessionmaker, nc)
            census = Census(app.state.sessionmaker, app.state.http)
            collector = BisCollector(app.state.sessionmaker, nc, app.state.http)
            # liegengebliebene Abrufe vom letzten Lauf, der tägliche Armory-Abruf, der Sammler der BiS-Listen
            # und die Zählung daraus; laufen neben dem Webserver
            tasks = [asyncio.create_task(app.state.characters.resume()),
                     asyncio.create_task(app.state.armory.daily()),
                     asyncio.create_task(collector.run()),
                     asyncio.create_task(census.daily())]
        app.state.poe_prices = None
        if settings.hub_poe_enabled:
            agent = f"NexHub/{settings.hub_version} (+https://github.com/DerWaschsalon/nexhub)"
            ninja = PoeNinja(app.state.http, agent)
            app.state.poe_prices = PoePrices(app.state.sessionmaker, ninja, settings)
            tasks.append(asyncio.create_task(app.state.poe_prices.run(after_poe_refresh)))
        yield
        for task in tasks:
            task.cancel()  # ein Neustart soll nicht auf NC warten; der Rest kommt beim nächsten Start
        if http is None:
            await app.state.http.aclose()
        await engine.dispose()

    app = FastAPI(title="NexHub", version=settings.hub_version, lifespan=lifespan,
                  docs_url="/api/docs", openapi_url="/api/openapi.json", redoc_url=None)
    app.state.settings = settings
    for router in ROUTERS:
        app.include_router(router)

    @app.middleware("http")
    async def check_origin(request: Request, call_next):
        """Schutz vor fremden Seiten, die im Namen des Browsers etwas auslösen (CSRF).

        Gilt für alles, was etwas ändert und mit Sitzungscookie kommt. Anfragen ohne Cookie
        (später z. B. Geräte mit eigenem Token) betrifft das nicht.
        """
        if (request.method not in SAFE_METHODS and SESSION_COOKIE in request.cookies
                and request.headers.get("origin") != settings.origin):
            return JSONResponse({"detail": "Fremde Herkunft"}, status_code=403)
        return await call_next(request)

    @app.get("/api/health", tags=["system"])
    async def health(db: DB) -> dict:
        await db.execute(text("SELECT 1"))
        return {"ok": True}

    if settings.hub_web_dir:
        _serve_web(app, settings.hub_web_dir.resolve())
    return app


def _serve_web(app: FastAPI, web) -> None:
    """Gebaute Web-Oberfläche ausliefern; unbekannte Pfade bekommen die App-Hülle 200.html."""

    @app.get("/{path:path}", include_in_schema=False)
    async def spa(path: str) -> FileResponse:
        if path == "api" or path.startswith("api/"):
            raise HTTPException(404)
        file = (web / path).resolve()
        if path and file.is_file() and file.is_relative_to(web):
            # Dateien unter _app/immutable tragen einen Hash im Namen und ändern sich nie
            cache = "public, max-age=31536000, immutable" if path.startswith("_app/immutable/") else "no-cache"
            return FileResponse(file, headers={"Cache-Control": cache})
        return FileResponse(web / "200.html", headers={"Cache-Control": "no-cache"})

