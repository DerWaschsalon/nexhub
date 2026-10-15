"""AION-2-DPS: eigener Mitschnitt oder der Stream-Overlay-Server des A2Tools DPS Meter.

Quelle `capture` (Standard): Der Daemon startet mit dem Spiel `deckbar-capture` (capture/ im
Repo, Kern des A2Tools-Meters ohne Oberfläche, siehe capture.py) und bekommt von dort die Zeilen.

Quellen `auto`/`manual`: Das Meter (github.com/taengu/A2Tools-DPS-Meter) liest selbst die
Spielpakete mit und bietet für OBS einen kleinen HTTP-Server an (Einstellungen → Stream-Overlay,
Port 18731). `/overlay/events?key=…` liefert etwa dreimal pro Sekunde den aktuellen Stand als
Server-Sent Events:

    {"v":1,"target":"Boss","mode":"bossTargets","timeMs":83000,"hp":42.5,
     "rows":[{"name":"…","cls":"cleric","dps":18432,"dmg":1529856,"pct":31.2,"you":true}]}

Daraus wird der State-Schlüssel `dps` (gekürzt, siehe `compact`) und `dps_active`
(gerade Schaden im Kampf). Endet ein Kampf, bekommen `fight_listeners` den letzten Stand mit
Gruppen-Flag (`fight_view`, z. B. für den Discord-Bot in bot.py). Port und Schlüssel stehen in
den Einstellungen des Meters (settings.json) und werden im Modus „auto“ von dort gelesen. Beide
Quellen liefern dasselbe Zeilenformat, deckbar-capture baut es wie das Stream-Overlay
(capture/src/view.rs).
"""
from __future__ import annotations

import asyncio
import json
import logging
import os
import time
from pathlib import Path
from typing import Any, Awaitable, Callable, Literal

import aiohttp
import yaml
from pydantic import Field, ValidationError

from .capture import Capture
from .config import ID, _atomic_write, _Strict
from .state import State

log = logging.getLogger(__name__)

DEFAULT_PORT = 18731
MAX_ROWS = 8
RETRY_S = 3
# Ohne Snapshot (auch ohne „: ping“ alle 15 s) gilt die Verbindung als tot
READ_TIMEOUT_S = 40
# Wie lange ohne neuen Schaden noch „im Kampf“, wenn return_after = 0 (nie zurück)
DEFAULT_IDLE_S = 30
CLASSES = ("gladiator", "templar", "ranger", "assassin", "sorcerer", "cleric", "spiritmaster", "chanter", "brawler")

Status = Literal["off", "no_meter", "overlay_off", "connecting", "bad_key", "connected",
                 "no_capture", "no_game", "no_caps", "capturing"]
LIVE = ("connected", "capturing")
STATUS_TEXT = {
    "off": "ausgeschaltet",
    "no_capture": "deckbar-capture nicht gefunden",
    "no_game": "wartet auf AION 2",
    "no_caps": "deckbar-capture ohne Mitschnitt-Rechte",
    "capturing": "Mitschnitt läuft",
    "no_meter": "A2Tools DPS Meter läuft nicht",
    "overlay_off": "Stream-Overlay im A2Tools-Meter ist aus",
    "connecting": "verbinde …",
    "bad_key": "Schlüssel abgelehnt",
    "connected": "verbunden",
}


class DpsSettings(_Strict):
    enabled: bool = True
    # capture = eigener Mitschnitt (deckbar-capture); auto = Stream-Overlay des A2Tools-Meters mit
    # Port + Schlüssel aus dessen Einstellungen; manual = dasselbe mit Port + Schlüssel von Hand
    source: Literal["capture", "auto", "manual"] = "capture"
    # deckbar-capture: fester Pfad (leer = PATH, sonst capture/target/release im Repo)
    capture_bin: str = Field("", max_length=300)
    # Sprache für Boss- und Skillnamen (Daten des Meters)
    lang: Literal["de", "en", "es", "fr", "ja", "ko", "pt", "ru", "zh-Hans", "zh-Hant"] = "en"
    port: int = Field(DEFAULT_PORT, ge=1024, le=65535)
    key: str = Field("", max_length=128)
    # Bei Kampfbeginn auf diese Seite wechseln (None = nie)
    auto_page: ID | None = None
    # Sekunden ohne neuen Schaden, bis die vorige Seite zurückkommt (0 = auf der DPS-Seite bleiben)
    return_after: int = Field(20, ge=0, le=600)


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


def _int(v: Any) -> int:
    try:
        return max(0, int(v))
    except (TypeError, ValueError):
        return 0


def compact(snap: dict, limit: int = MAX_ROWS) -> dict:
    """Snapshot des Meters → State-Wert `dps` (nur, was das Display braucht)."""
    rows = []
    for r in snap.get("rows") or []:
        if not isinstance(r, dict) or len(rows) >= limit:
            continue
        cls = r.get("cls")
        pct = r.get("pct")
        rows.append({
            "name": str(r.get("name") or "?")[:24],
            "cls": cls if cls in CLASSES else None,
            "dps": _int(r.get("dps")),
            "dmg": _int(r.get("dmg")),
            "pct": round(float(pct), 1) if isinstance(pct, (int, float)) else 0.0,
            "you": bool(r.get("you")),
        })
    hp = snap.get("hp")
    return {
        "target": str(snap.get("target") or "")[:40],
        "time": _int(snap.get("timeMs")) // 1000,
        "hp": round(float(hp), 1) if isinstance(hp, (int, float)) else None,
        "rows": rows,
    }


def fight_view(snap: dict) -> dict:
    """Snapshot → Endstand eines Kampfs für Weitergaben (bot.py): alle Zeilen, mit Ziel-ID, Boss und
    Gruppen-Flag. `party` ist None, wenn die Quelle es nicht kennt (A2Tools-Stream, altes deckbar-capture)."""
    rows = []
    for r in snap.get("rows") or []:
        if not isinstance(r, dict):
            continue
        cls = r.get("cls")
        party = r.get("party")
        rows.append({
            "name": str(r.get("name") or "?")[:32],
            "cls": cls if cls in CLASSES else None,
            "dps": _int(r.get("dps")),
            "dmg": _int(r.get("dmg")),
            "you": bool(r.get("you")),
            "party": party if isinstance(party, bool) else None,
        })
    hp = snap.get("hp")
    tid = snap.get("targetId")
    return {
        "target": str(snap.get("target") or "")[:80],
        "target_id": tid if isinstance(tid, int) else None,
        "boss": bool(snap.get("boss")),
        "time": _int(snap.get("timeMs")) // 1000,
        "hp": round(float(hp), 1) if isinstance(hp, (int, float)) else None,
        "rows": rows,
    }


def total_damage(value: dict | None) -> int:
    return sum(r["dmg"] for r in value["rows"]) if value else 0


CombatListener = Callable[[bool], Awaitable[None]]
FightListener = Callable[[dict], Awaitable[None]]


class DpsFeed:
    def __init__(self, state: State, config_dir: Path, on_combat: CombatListener | None = None) -> None:
        self.state = state
        self.path = config_dir / "dps.yaml"
        self.on_combat = on_combat
        self.settings = self._load()
        self.status: Status = "off"
        self.detail = ""
        self.port: int | None = None
        self.status_listeners: list[Callable[[], Awaitable[None]]] = []
        # Kampfende: letzter Stand mit Zeilen (fight_view), z. B. für den Discord-Bot
        self.fight_listeners: list[FightListener] = []
        self.fight: dict | None = None
        self._pending: set[asyncio.Task] = set()
        self._wake = asyncio.Event()
        self._last_total = 0
        self._last_change = 0.0
        self.capture = Capture(self._on_view, self._on_capture_change)

    # ------------------------------------------------------------ Einstellungen
    def _load(self) -> DpsSettings:
        try:
            data = yaml.safe_load(self.path.read_text()) or {}
            return DpsSettings.model_validate(data)
        except FileNotFoundError:
            return DpsSettings()
        except (yaml.YAMLError, ValidationError) as e:
            log.error("%s ungültig, nutze Standardwerte: %s", self.path, e)
            return DpsSettings()

    def save(self, settings: DpsSettings) -> None:
        header = "# AION-2-DPS – wird von der Web-UI überschrieben.\n"
        text = yaml.safe_dump(settings.model_dump(exclude_none=True), sort_keys=False, allow_unicode=True)
        _atomic_write(self.path, header + text, 0o600)  # enthält ggf. den Overlay-Schlüssel
        self.settings = settings
        self._wake.set()

    @property
    def idle_after(self) -> int:
        return self.settings.return_after or DEFAULT_IDLE_S

    def info(self) -> dict:
        s = self.settings.model_dump()
        s["key"] = "•" * 8 if s["key"] else ""  # der Schlüssel verlässt den Daemon nicht
        a2t = read_a2tools()
        a2t.pop("key")
        return {
            "settings": s,
            "status": self.status,
            "status_text": STATUS_TEXT[self.status],
            "detail": self.detail,
            "port": self.port,
            "a2tools": a2t,
            "capture": self.capture.info(),
        }

    # ------------------------------------------------------------ Status
    async def _set_status(self, status: Status, detail: str = "") -> None:
        if (status, detail) == (self.status, self.detail):
            return
        if status != self.status:
            log.info("DPS-Meter: %s%s", STATUS_TEXT[status], f" ({detail})" if detail else "")
        self.status, self.detail = status, detail
        if status not in LIVE:
            await self._apply(None)
        for fn in self.status_listeners:
            await fn()

    async def _apply(self, value: dict | None, baseline: bool = False, fight: dict | None = None) -> None:
        """Neuer Stand vom Meter; erkennt Kampfbeginn am wachsenden Gesamtschaden.
        baseline: erster Stand nach dem Verbinden – ein alter Kampf zählt nicht als Beginn.
        fight: derselbe Stand als fight_view (alle Zeilen), wird zum Endstand des Kampfs."""
        was_active = bool(self.state.values.get("dps_active"))
        if fight and fight["rows"] and not baseline:
            self.fight = fight
        total = total_damage(value)
        # Schaden kam hinzu (auch: Meter hat zurückgesetzt und ein neuer Kampf läuft)
        hit = total > 0 and total != self._last_total and not baseline
        if hit:
            self._last_change = time.monotonic()
        self._last_total = total
        active = value is not None and (was_active or hit)
        self.state.update(dps=value, dps_active=active)
        if active != was_active:
            await self._combat(active)

    async def check_idle(self) -> None:
        if self.state.values.get("dps_active") and time.monotonic() - self._last_change >= self.idle_after:
            self.state.update(dps_active=False)
            await self._combat(False)

    async def _combat(self, active: bool) -> None:
        if self.on_combat:
            await self.on_combat(active)
        if active:
            return
        fight, self.fight = self.fight, None
        if fight:
            # entkoppelt: ein langsamer Zuhörer (Netz, bis 20 s) darf den Feed nicht anhalten
            for fn in self.fight_listeners:
                t = asyncio.ensure_future(self._notify_fight(fn, fight))
                self._pending.add(t)
                t.add_done_callback(self._pending.discard)

    @staticmethod
    async def _notify_fight(fn: FightListener, fight: dict) -> None:
        try:
            await fn(fight)
        except Exception:
            log.exception("Kampfende-Zuhörer")

    async def _sleep(self, seconds: float) -> None:
        """Wartet, wacht aber sofort auf, wenn sich die Einstellungen ändern."""
        try:
            await asyncio.wait_for(self._wake.wait(), seconds)
        except TimeoutError:
            pass

    # ------------------------------------------------------------ Verbindung
    def _target(self) -> tuple[int, str] | None:
        s = self.settings
        if s.source == "manual":
            return s.port, s.key
        a2t = read_a2tools()
        if not a2t["installed"]:
            return None
        if not a2t["enabled"] or not a2t["key"]:
            return -1, ""
        return a2t["port"], a2t["key"]

    # ------------------------------------------------------------ eigener Mitschnitt
    async def _on_view(self, view: dict | None, first: bool) -> None:
        if self.status == "capturing":
            await self._apply(compact(view) if view else None, baseline=first,
                              fight=fight_view(view) if view else None)

    async def _on_capture_change(self) -> None:
        c = self.capture
        if self.settings.source != "capture" or not self.settings.enabled:
            return
        if c.phase == "no_binary":
            await self._set_status("no_capture")
        elif c.phase == "no_game":
            await self._set_status("no_game")
        elif c.phase == "no_caps":
            await self._set_status("no_caps")
        elif c.phase == "crashed":
            await self._set_status("no_game", c.error)
        elif c.phase == "starting":
            await self._set_status("connecting")
        else:
            port = c.status.get("port")
            await self._set_status("capturing", f"Spielserver-Port {port}" if port else "wartet auf Kampfdaten")
        for fn in self.status_listeners:  # Ping/Port ändern sich ohne Statuswechsel
            await fn()

    async def watch(self) -> None:
        async def idle_loop() -> None:
            while True:
                await asyncio.sleep(1)
                await self.check_idle()

        idle = asyncio.ensure_future(idle_loop())
        timeout = aiohttp.ClientTimeout(total=None, connect=3, sock_read=READ_TIMEOUT_S)
        current: list[asyncio.Task] = []  # laufender Mitschnitt/Stream, bei Abbruch mitbeenden
        try:
            async with aiohttp.ClientSession(timeout=timeout) as session:
                while True:
                    self._wake.clear()
                    if not self.settings.enabled:
                        self.port = None
                        await self._set_status("off")
                        await self._wake.wait()
                        continue
                    if self.settings.source == "capture":
                        self.port = None
                        job = asyncio.ensure_future(self.capture.run(self.settings.capture_bin, self.settings.lang))
                        wake = asyncio.ensure_future(self._wake.wait())
                        current[:] = [job, wake]
                        await asyncio.wait({job, wake}, return_when=asyncio.FIRST_COMPLETED)
                        for t in (job, wake):
                            t.cancel()
                        await asyncio.gather(job, return_exceptions=True)  # Programm sauber beenden
                        if not self._wake.is_set():
                            await self._sleep(RETRY_S)
                        continue
                    target = self._target()
                    if target is None:
                        await self._set_status("no_meter", "nicht installiert")
                        await self._sleep(10)
                        continue
                    port, key = target
                    if port < 0:
                        await self._set_status("overlay_off")
                        await self._sleep(5)
                        continue
                    self.port = port
                    # Einstellungen geändert → Verbindung sofort abbrechen und neu aufbauen
                    stream = asyncio.ensure_future(self._stream(session, port, key))
                    wake = asyncio.ensure_future(self._wake.wait())
                    current[:] = [stream, wake]
                    await asyncio.wait({stream, wake}, return_when=asyncio.FIRST_COMPLETED)
                    for t in (stream, wake):
                        t.cancel()
                    if not self._wake.is_set():
                        await self._sleep(RETRY_S)
        finally:
            idle.cancel()
            # Modul aus: auch deckbar-capture beenden (asyncio.wait bricht die inneren Tasks nicht ab)
            for t in current:
                t.cancel()
            await asyncio.gather(*current, return_exceptions=True)

    async def _stream(self, session: aiohttp.ClientSession, port: int, key: str) -> None:
        url = f"http://127.0.0.1:{port}/overlay/events"
        if self.status not in ("connected", "no_meter"):
            await self._set_status("connecting")
        try:
            async with session.get(url, params={"key": key}) as resp:
                if resp.status == 403:
                    await self._set_status("bad_key")
                    return
                if resp.status != 200 or not resp.content_type.startswith("text/event-stream"):
                    await self._set_status("no_meter", f"Antwort {resp.status} auf Port {port}")
                    return
                await self._set_status("connected")
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
                        await self._apply(compact(snap), baseline=first, fight=fight_view(snap))
                        first = False
            await self._set_status("no_meter", "Verbindung beendet")
        except aiohttp.ClientConnectorError:
            await self._set_status("no_meter")
        except (aiohttp.ClientError, TimeoutError) as e:
            await self._set_status("no_meter", type(e).__name__)
