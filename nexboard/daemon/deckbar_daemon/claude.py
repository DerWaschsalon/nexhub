"""Claude-Nutzung: Auslastung des Claude-Abos (Sitzung über 5 h, Woche) für die Kachel `claude`.

Fragt denselben Endpunkt ab wie `/usage` in Claude Code, mit dessen Anmeldung aus
~/.claude/.credentials.json. Das Token verlängert Claude Code selbst, hier wird es nur gelesen.
Der Endpunkt ist nicht offiziell dokumentiert: Ändert er sich, zeigt die Kachel „–“.
Abgefragt wird nur, solange eine Claude-Kachel im Layout ist.
"""
from __future__ import annotations

import asyncio
import json
import logging
import os
import time
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any, Callable

import aiohttp

from .state import State

log = logging.getLogger(__name__)

URL = "https://api.anthropic.com/api/oauth/usage"
EVERY_S = 300  # die Werte ändern sich nur mit der Nutzung, öfter fragen bringt nichts
LOOK_S = 10    # so schnell erscheinen Werte, nachdem eine Kachel ins Layout kam
# Schlüssel auf der Leiste → Feld in der Antwort
LIMITS = {"session": "five_hour", "week": "seven_day"}
WEEKDAYS = ("Mo", "Di", "Mi", "Do", "Fr", "Sa", "So")


def credentials_path() -> Path:
    base = os.environ.get("CLAUDE_CONFIG_DIR")
    return (Path(base) if base else Path.home() / ".claude") / ".credentials.json"


def reset_text(iso: str, now: datetime) -> str:
    """Rücksetzzeit in Ortszeit: heute nur die Uhrzeit, sonst mit Wochentag („Fr 00:59“)."""
    # Der Endpunkt nennt x:59:59.6 – auf die volle Minute runden, wie Claude Code es anzeigt
    at = (datetime.fromisoformat(iso) + timedelta(seconds=30)).astimezone()
    clock = at.strftime("%H:%M")
    return clock if at.date() == now.date() else f"{WEEKDAYS[at.weekday()]} {clock}"


def summary(data: dict[str, Any], now: datetime) -> dict[str, dict]:
    """Antwort des Endpunkts → {"session": {"pct": 31, "reset": "12:00"}, "week": {…}}."""
    out = {}
    for key, field in LIMITS.items():
        limit = data.get(field) or {}
        if limit.get("utilization") is None:
            continue
        out[key] = {"pct": round(limit["utilization"]),
                    "reset": reset_text(limit["resets_at"], now) if limit.get("resets_at") else ""}
    return out


class ClaudeUsage:
    def __init__(self, state: State, wanted: Callable[[], bool]) -> None:
        self.state = state
        self.wanted = wanted  # True, solange eine Claude-Kachel im Layout ist
        self._error = ""

    async def watch(self) -> None:
        last = -EVERY_S
        async with aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=15)) as http:
            while True:
                if self.wanted() and time.monotonic() - last >= EVERY_S:
                    last = time.monotonic()
                    self.state.update(claude=await self._fetch(http))
                await asyncio.sleep(LOOK_S)

    async def _fetch(self, http: aiohttp.ClientSession) -> dict | None:
        try:
            token = self._token()
            headers = {"Authorization": f"Bearer {token}", "anthropic-beta": "oauth-2025-04-20"}
            async with http.get(URL, headers=headers) as r:
                r.raise_for_status()
                data = await r.json()
            result = summary(data, datetime.now().astimezone())
        except (OSError, ValueError, KeyError, TypeError, aiohttp.ClientError, TimeoutError) as e:
            self._failed(str(e) or type(e).__name__)
            return None
        self._error = ""
        return result or None

    def _token(self) -> str:
        oauth = json.loads(credentials_path().read_text())["claudeAiOauth"]
        if oauth.get("expiresAt", 0) < time.time() * 1000:
            raise ValueError("Anmeldung abgelaufen – Claude Code einmal starten")
        return oauth["accessToken"]

    def _failed(self, error: str) -> None:
        # nur beim ersten Mal melden, sonst stünde der Fehler alle 5 Minuten im Log
        if error != self._error:
            log.warning("Claude-Nutzung nicht abrufbar: %s", error)
        self._error = error
