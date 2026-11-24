"""Das A2Tools-Meter als Quelle der Kampfdaten: seine Einstellungen lesen und seinen Stream-Overlay-Server
abhören (Quellen „auto“ und „manual“; der eigene Mitschnitt ist capture.py).

Das Meter (github.com/taengu/A2Tools-DPS-Meter) liest selbst die Spielpakete mit und bietet für OBS einen
kleinen HTTP-Server an (Einstellungen → Stream-Overlay, Port 18731). `/overlay/events?key=…` liefert etwa
dreimal pro Sekunde den aktuellen Stand als Server-Sent Events:

    {"v":1,"target":"Boss","mode":"bossTargets","timeMs":83000,"hp":42.5,
     "rows":[{"name":"…","cls":"cleric","dps":18432,"dmg":1529856,"pct":31.2,"you":true}]}

Port und Schlüssel stehen in den Einstellungen des Meters (settings.json).
"""
from __future__ import annotations

import json
import os
from collections.abc import Awaitable, Callable
from pathlib import Path
from typing import Any

import aiohttp

DEFAULT_PORT = 18731
READ_TIMEOUT_S = 40  # so lange ohne Daten gilt die Verbindung als tot

StatusListener = Callable[[str, str], Awaitable[Any]]  # (Status, Einzelheit)
SnapshotListener = Callable[[dict, bool], Awaitable[None]]  # (Stand, erster seit dem Verbinden?)


def a2tools_settings_path() -> Path:
    base = os.environ.get("XDG_DATA_HOME") or str(Path.home() / ".local" / "share")
    return Path(os.environ.get("DECKBAR_A2TOOLS_SETTINGS", Path(base) / "com.a2tools.dps-meter" / "settings.json"))


def read_a2tools(path: Path | None = None) -> dict[str, Any]:
    """Overlay-Einstellungen des Meters: installed, enabled, port, key."""
    path = path or a2tools_settings_path()
    try:
        data = json.loads(path.read_text())
    except FileNotFoundError:
        return {"installed": False, "enabled": False, "port": DEFAULT_PORT, "key": ""}
    except (OSError, ValueError):
        data = {}
    if not isinstance(data, dict):
        data = {}
    try:
        port = int(str(data.get("dpsMeter.streamOverlayPort", DEFAULT_PORT)).strip())
    except ValueError:
        port = DEFAULT_PORT
    return {
        "installed": True,
        "enabled": data.get("dpsMeter.streamOverlay") == "true",
        "port": port,
        "key": str(data.get("dpsMeter.streamOverlayKey") or ""),
    }


class MeterStream:
    """Eine Verbindung zum Stream-Overlay des Meters. `run()` meldet Status und jeden Stand über die
    Rückrufe und endet, wenn die Verbindung endet oder nicht zustande kommt."""

    def __init__(self, session: aiohttp.ClientSession, port: int, key: str, on_status: StatusListener,
                 on_snapshot: SnapshotListener) -> None:
        self.session, self.port, self.key = session, port, key
        self.on_status, self.on_snapshot = on_status, on_snapshot

    async def run(self) -> None:
        url = f"http://127.0.0.1:{self.port}/overlay/events"
        try:
            async with self.session.get(url, params={"key": self.key}) as resp:
                if resp.status == 403:
                    await self.on_status("bad_key", "")
                    return
                if resp.status != 200 or not resp.content_type.startswith("text/event-stream"):
                    await self.on_status("no_meter", f"Antwort {resp.status} auf Port {self.port}")
                    return
                await self.on_status("connected", "")
                await self._read(resp)
            await self.on_status("no_meter", "Verbindung beendet")
        except aiohttp.ClientConnectorError:
            await self.on_status("no_meter", "")
        except (aiohttp.ClientError, TimeoutError) as e:
            await self.on_status("no_meter", type(e).__name__)

    async def _read(self, resp: aiohttp.ClientResponse) -> None:
        """Jede `data:`-Zeile ist ein Stand; kaputte Zeilen überspringen."""
        first = True
        async for raw in resp.content:
            line = raw.decode(errors="replace").rstrip("\r\n")
            if not line.startswith("data:"):
                continue
            try:
                snap = json.loads(line[5:].strip())
            except ValueError:
                continue
            if isinstance(snap, dict):
                await self.on_snapshot(snap, first)
                first = False
