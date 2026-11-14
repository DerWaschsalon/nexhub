"""Steuer-API von TheWashBot: der Hub meldet Runs, der Bot postet sie in Discord."""
from __future__ import annotations

import logging
from typing import Any

import httpx

from .config import Settings

log = logging.getLogger(__name__)


async def tell_bot(http: httpx.AsyncClient, settings: Settings, action: str, payload: dict[str, Any]) -> None:
    """An die Steuer-API von TheWashBot, z. B. `run-link` (Link an einen Post hängen), `run` (Run posten).
    Ein Fehler hier darf den Aufrufer nicht stören, er wird nur geloggt."""
    try:
        r = await http.post(f"{settings.bot_control_url}/control/{action}", json=payload, timeout=10,
                            headers={"Authorization": f"Bearer {settings.bot_control_key}"})
    except httpx.HTTPError as e:
        log.warning("Bot nicht erreichbar (%s): %s", action, e)
        return
    if r.status_code != 200:
        log.warning("Bot lehnt %s ab (%d): %s", action, r.status_code, r.text[:200])
