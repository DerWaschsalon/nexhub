"""HTTP für alle Module: nur localhost, einheitliche Fehlerantworten, JSON-Eingaben lesen."""
from __future__ import annotations

from collections.abc import Awaitable, Callable
from typing import Any

from aiohttp import web
from nexcore.errors import ApiError, invalid
from pydantic import ValidationError

LOCAL_HOSTS = {"127.0.0.1", "::1", "localhost"}
Handler = Callable[[web.Request], Awaitable[web.StreamResponse]]


@web.middleware
async def local_only(request: web.Request, handler: Handler) -> web.StreamResponse:
    """Alles außer /ws nur von localhost, plus Host-/Origin-Prüfung gegen DNS-Rebinding."""
    if request.path == "/ws":
        return await handler(request)
    remote = request.remote or ""
    if remote.startswith("::ffff:"):
        remote = remote[7:]
    host = (request.host or "").rsplit(":", 1)[0].strip("[]")
    if remote not in LOCAL_HOSTS or host not in LOCAL_HOSTS:
        raise web.HTTPForbidden(text="Die NexBoard-Konfiguration ist nur über localhost erreichbar.")
    origin = request.headers.get("Origin")
    if origin and request.method not in ("GET", "HEAD"):
        o_host = origin.split("://", 1)[-1].rsplit(":", 1)[0].strip("[]")
        if o_host not in LOCAL_HOSTS:
            raise web.HTTPForbidden(text="fremder Origin")
    return await handler(request)


@web.middleware
async def api_errors(request: web.Request, handler: Handler) -> web.StreamResponse:
    """ApiError und Prüffehler werden zu {"error": …} mit passendem Status; Handler werfen nur."""
    try:
        return await handler(request)
    except ValidationError as e:
        error = invalid(e)
    except ApiError as e:
        error = e
    return web.json_response(error.body(), status=error.status)


async def read_object(request: web.Request) -> dict[str, Any]:
    try:
        data = await request.json()
    except ValueError:
        data = None
    if not isinstance(data, dict):
        raise ApiError(400, "kein JSON-Objekt")
    return data


def ok(**data: Any) -> web.Response:
    return web.json_response({"ok": True, **data})
