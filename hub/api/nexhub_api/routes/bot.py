"""TheWashBot steuern: reicht Anfragen an die Steuer-API des Bots durch (nur Admins).

`/api/admin/bot/<pfad>` → `<BOT_CONTROL_URL>/control/<pfad>` mit dem gemeinsamen Schlüssel.
Was erlaubt ist und wie Werte geprüft werden, entscheidet der Bot (bot/bot/cogs/control.py);
der Hub prüft nur, dass ein Admin fragt. Der Name des Admins geht als `X-Hub-User` mit, der Bot
schreibt ihn ins Discord-Audit-Log.
"""
from __future__ import annotations

import logging
import re
from urllib.parse import quote

import httpx
from fastapi import APIRouter, Depends, HTTPException, Request, Response

from ..deps import AdminUser, SettingsDep, require_admin

log = logging.getLogger(__name__)

router = APIRouter(prefix="/api/admin/bot", tags=["bot"], dependencies=[Depends(require_admin)])

# Nur einfache Pfadteile, damit nichts außerhalb von /control/ erreichbar ist
PATH = re.compile(r"[A-Za-z0-9_-]+(/[A-Za-z0-9_-]+)*")
MAX_BODY = 256 * 1024


@router.api_route("/{path:path}", methods=["GET", "POST", "PUT", "DELETE"])
async def forward(path: str, request: Request, admin: AdminUser, settings: SettingsDep) -> Response:
    if not settings.bot_configured:
        raise HTTPException(503, "Bot ist nicht mit dem Hub verbunden (BOT_CONTROL_URL/BOT_CONTROL_KEY fehlen)")
    if not PATH.fullmatch(path):
        raise HTTPException(404, "Gibt es nicht")
    body = await request.body()
    if len(body) > MAX_BODY:
        raise HTTPException(413, "Anfrage zu groß")
    headers = {"Authorization": f"Bearer {settings.bot_control_key}",
               # Header sind nur Latin-1, Discord-Namen nicht
               "X-Hub-User": quote(admin.name, safe="")}
    if body:
        headers["Content-Type"] = "application/json"
    http: httpx.AsyncClient = request.app.state.http
    try:
        r = await http.request(request.method, f"{settings.bot_control_url}/control/{path}",
                               content=body or None, headers=headers, timeout=15)
    except httpx.TimeoutException:
        raise HTTPException(504, "Bot antwortet nicht") from None
    except httpx.HTTPError as e:
        log.warning("Bot nicht erreichbar: %s", e)
        raise HTTPException(502, "Bot ist nicht erreichbar") from None
    if r.status_code == 401:
        # Nicht als 401 weitergeben, sonst hielte die Web-Oberfläche den Admin für abgemeldet
        log.error("Bot lehnt BOT_CONTROL_KEY ab")
        raise HTTPException(502, "Bot lehnt den Schlüssel ab (BOT_CONTROL_KEY stimmt nicht überein)")
    if r.status_code == 204:
        return Response(status_code=204)
    if r.headers.get("content-type", "").split(";")[0] != "application/json":
        raise HTTPException(502, f"Unerwartete Antwort vom Bot ({r.status_code})")
    return Response(r.content, status_code=r.status_code, media_type="application/json")
