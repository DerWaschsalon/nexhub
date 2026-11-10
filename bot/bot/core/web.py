"""Ein Webserver für den ganzen Bot: Module und Verwaltung melden Routen an, der WebHost liefert sie aus.

Zwei Seiten, weil Caddy auf dem VPS nur die öffentlichen Pfade nach draußen gibt:

- öffentlich (Port 8789, `AION_PORT`): Runs aus dem NexBoard und die Bestenliste. Jedes Modul prüft
  dort selbst, wer anfragt (z. B. AION-Token).
- intern (Port 8790, `CONTROL_PORT`): Steuer-API für den NexHub unter `/control/…`, nur mit
  `Authorization: Bearer <BOT_CONTROL_KEY>`, Antworten immer JSON. Ohne gültigen Schlüssel bleibt
  diese Seite aus.

Beide Seiten auf einen Port zu legen ist nur noch eine Frage der Konfiguration (Caddy), nicht des Codes.
"""

from __future__ import annotations

import hmac
import json
import logging
import os
import urllib.parse
from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field
from typing import Any

import discord
from aiohttp import web

from ..errors import UserError
from ..hubpages import ApiError

log = logging.getLogger(__name__)

PUBLIC_PORT = 8789
CONTROL_PORT = 8790
MIN_KEY_LENGTH = 24
CONTROL_MAX_BODY = 256 * 1024

Handler = Callable[[web.Request], Awaitable[web.StreamResponse]]
JsonHandler = Callable[[web.Request], Awaitable[Any]]  # gibt JSON-Daten zurück, None heißt 204


@dataclass(frozen=True)
class Route:
    method: str
    path: str
    handler: Handler


@dataclass
class RouteTable:
    """Sammelt die Routen beim Start. `control` für die Steuer-API (JSON, mit Schlüssel),
    `public` für alles, was von außen kommt (eigene Antworten, eigene Prüfung)."""
    public: list[Route] = field(default_factory=list)
    internal: list[Route] = field(default_factory=list)
    public_max_body: int = 1024 * 1024

    def control(self, method: str, path: str, handler: JsonHandler) -> None:
        if not path.startswith("/control/"):
            raise ValueError(f"Steuer-API-Pfad muss mit /control/ beginnen: {path}")
        self.internal.append(Route(method, path, as_json(handler)))

    def open(self, method: str, path: str, handler: Handler, *, max_body: int = 0) -> None:
        self.public.append(Route(method, path, handler))
        self.public_max_body = max(self.public_max_body, max_body)


def as_json(handler: JsonHandler) -> Handler:
    """Macht aus dem Rückgabewert eines Handlers die HTTP-Antwort."""

    async def respond(request: web.Request) -> web.StreamResponse:
        result = await handler(request)
        if result is None:
            return web.Response(status=204)
        return web.json_response(result)

    return respond


def only_while_on(allowed: Callable[[], bool], name: str, handler: Handler) -> Handler:
    """Routen eines ausgeschalteten Moduls antworten mit 503 statt mit Daten."""

    async def call(request: web.Request) -> web.StreamResponse:
        if not allowed():
            return web.json_response({"detail": f"„{name}“ ist gerade ausgeschaltet"}, status=503)
        return await handler(request)

    return call


# ---- Hilfen für Steuer-API-Handler ------------------------------------------------------------

async def json_body(request: web.Request) -> dict[str, Any]:
    try:
        data = await request.json()
    except (json.JSONDecodeError, UnicodeDecodeError):
        raise ApiError(400, "JSON erwartet") from None
    if not isinstance(data, dict):
        raise ApiError(400, "JSON-Objekt erwartet")
    return data


def hub_user(request: web.Request) -> str:
    # Der Hub schickt den Namen URL-kodiert, weil Header nur Latin-1 können
    return urllib.parse.unquote(request.headers.get("X-Hub-User", "")).strip()[:60]


def audit_reason(request: web.Request) -> str:
    """Grund im Discord-Audit-Log, wenn jemand im Hub etwas am Server ändert."""
    who = hub_user(request)
    return f"NexHub: {who}" if who else "NexHub"


def find_guild(client: discord.Client) -> discord.Guild | None:
    """Der Server, den der Hub verwaltet: aus DEV_GUILD_ID, sonst der erste, auf dem der Bot ist."""
    gid = os.getenv("DEV_GUILD_ID", "").strip()
    if gid.isdigit():
        return client.get_guild(int(gid))
    return client.guilds[0] if client.guilds else None


def hub_guild(client: discord.Client) -> discord.Guild:
    guild = find_guild(client)
    if guild is None:
        raise ApiError(503, "Bot ist mit keinem Discord-Server verbunden")
    return guild


# ---- Server -----------------------------------------------------------------------------------

def control_app(table: RouteTable, key: str) -> web.Application:
    """Steuer-API: Schlüssel prüfen, Fehler einheitlich als {"detail": …}."""

    @web.middleware
    async def middleware(request: web.Request, handler: Handler) -> web.StreamResponse:
        scheme, _, token = request.headers.get("Authorization", "").partition(" ")
        if scheme.lower() != "bearer" or not hmac.compare_digest(token.encode(), key.encode()):
            return web.json_response({"detail": "Schlüssel fehlt oder falsch"}, status=401)
        try:
            return await handler(request)
        except ApiError as e:
            return web.json_response({"detail": e.detail}, status=e.status)
        except UserError as e:
            return web.json_response({"detail": str(e)}, status=400)
        except web.HTTPException as e:
            return web.json_response({"detail": e.reason}, status=e.status)
        except discord.Forbidden:
            return web.json_response({"detail": "Dafür fehlen dem Bot die Rechte auf dem Server"}, status=409)
        except discord.HTTPException as e:
            return web.json_response({"detail": f"Discord: {e.text or e.status}"}, status=502)
        except Exception:
            log.exception("Steuer-API: Fehler bei %s %s", request.method, request.path)
            return web.json_response({"detail": "Fehler im Bot, Details stehen im Log"}, status=500)

    app = web.Application(middlewares=[middleware], client_max_size=CONTROL_MAX_BODY)
    for r in table.internal:
        app.router.add_route(r.method, r.path, r.handler)
    return app


def public_app(table: RouteTable) -> web.Application:
    app = web.Application(client_max_size=table.public_max_body)
    for r in table.public:
        app.router.add_route(r.method, r.path, r.handler)
    return app


def control_key() -> str:
    """BOT_CONTROL_KEY, oder leer, wenn er fehlt oder zu kurz ist (dann bleibt die Steuer-API aus)."""
    key = os.getenv("BOT_CONTROL_KEY", "").strip()
    if not key:
        log.info("BOT_CONTROL_KEY fehlt – Steuer-API für den NexHub ist aus")
        return ""
    if len(key) < MIN_KEY_LENGTH:
        log.warning("BOT_CONTROL_KEY ist zu kurz (mindestens %d Zeichen) – Steuer-API bleibt aus", MIN_KEY_LENGTH)
        return ""
    return key


class WebHost:
    def __init__(self) -> None:
        self.runners: list[web.AppRunner] = []

    async def start(self, table: RouteTable) -> None:
        if table.public:
            port = int(os.getenv("AION_PORT", PUBLIC_PORT))
            await self._serve(public_app(table), "0.0.0.0", port)
            log.info("Öffentliche Endpunkte (Runs, Bestenliste) hören auf Port %d", port)
        key = control_key()
        if key and table.internal:
            port = int(os.getenv("CONTROL_PORT", CONTROL_PORT))
            await self._serve(control_app(table, key), os.getenv("CONTROL_HOST", "0.0.0.0"), port)
            log.info("Steuer-API hört auf Port %d", port)

    async def _serve(self, app: web.Application, host: str, port: int) -> None:
        runner = web.AppRunner(app)
        await runner.setup()
        await web.TCPSite(runner, host, port).start()
        self.runners.append(runner)

    async def stop(self) -> None:
        for runner in self.runners:
            await runner.cleanup()
        self.runners.clear()
