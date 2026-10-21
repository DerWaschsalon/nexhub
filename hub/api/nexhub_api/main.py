"""FastAPI-Anwendung: API unter /api, alles andere ist die statische Web-Oberfläche."""
from __future__ import annotations

import logging
from contextlib import asynccontextmanager
from typing import Annotated

import httpx
from fastapi import Depends, FastAPI, HTTPException
from fastapi.responses import FileResponse
from pydantic import BaseModel
from sqlalchemy import text
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from . import auth
from .auth import DB, require_user
from .config import Settings
from .models import User

log = logging.getLogger(__name__)


class Me(BaseModel):
    # Discord-IDs als Text: als Zahl verlieren sie in JavaScript die letzten Stellen
    discord_id: str
    username: str
    display_name: str | None
    avatar_url: str | None
    role: str


def avatar_url(user: User) -> str | None:
    if not user.avatar:
        return None
    return f"https://cdn.discordapp.com/avatars/{user.discord_id}/{user.avatar}.png?size=128"


def create_app(settings: Settings | None = None, http: httpx.AsyncClient | None = None) -> FastAPI:
    settings = settings or Settings()

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        engine = create_async_engine(settings.database_url, pool_pre_ping=True)
        app.state.sessionmaker = async_sessionmaker(engine, expire_on_commit=False)
        app.state.http = http or httpx.AsyncClient(timeout=10)
        if not settings.discord_configured:
            log.warning("DISCORD_CLIENT_ID/DISCORD_CLIENT_SECRET fehlen – Login ist aus")
        yield
        if http is None:
            await app.state.http.aclose()
        await engine.dispose()

    app = FastAPI(title="NexHub", lifespan=lifespan, docs_url="/api/docs", openapi_url="/api/openapi.json",
                  redoc_url=None)
    app.state.settings = settings
    app.include_router(auth.router)

    @app.get("/api/health")
    async def health(db: DB) -> dict:
        await db.execute(text("SELECT 1"))
        return {"ok": True, "login": settings.discord_configured}

    @app.get("/api/me")
    async def me(user: Annotated[User, Depends(require_user)]) -> Me:
        return Me(discord_id=str(user.discord_id), username=user.username, display_name=user.display_name,
                  avatar_url=avatar_url(user), role=user.role)

    if settings.hub_web_dir:
        web = settings.hub_web_dir.resolve()

        @app.get("/{path:path}", include_in_schema=False)
        async def spa(path: str) -> FileResponse:
            if path == "api" or path.startswith("api/"):
                raise HTTPException(404)
            file = (web / path).resolve()
            if path and file.is_file() and file.is_relative_to(web):
                # Dateien unter _app/immutable tragen einen Hash im Namen und ändern sich nie
                cache = "public, max-age=31536000, immutable" if path.startswith("_app/immutable/") else "no-cache"
                return FileResponse(file, headers={"Cache-Control": cache})
            # 200.html ist die leere Hülle der SvelteKit-App (adapter-static, fallback)
            return FileResponse(web / "200.html", headers={"Cache-Control": "no-cache"})

    return app
