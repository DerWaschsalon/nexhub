"""AION-2-Kampfdaten: wählt die Quelle, führt den Status und reicht jeden Stand an die Kampferkennung.

Quelle `capture` (Standard): Der Daemon startet mit dem Spiel `deckbar-capture` (capture/ im Repo, Kern des
A2Tools-Meters ohne Oberfläche, siehe capture.py) und bekommt von dort die Zeilen.
Quellen `auto`/`manual`: der Stream-Overlay-Server des A2Tools-Meters (a2tools_meter.py); bei „auto“ kommen
Port und Schlüssel aus den Einstellungen des Meters.

Aus jedem Stand wird der State `dps` (gekürzt, dps_view.compact) und `dps_active` (combat.py).
"""
from __future__ import annotations

import asyncio
import logging
from collections.abc import Awaitable, Callable
from pathlib import Path
from typing import Literal

import aiohttp
from nexcore.settings import ADVANCED, HIDDEN, SECRET, SettingsStore
from pydantic import Field

from .a2tools_meter import DEFAULT_PORT, READ_TIMEOUT_S, MeterStream, read_a2tools
from .capture import Capture
from .combat import CombatListener, CombatTracker
from .config import _Strict
from .dps_view import compact, fight_view
from .state import State

log = logging.getLogger(__name__)

SETTINGS_FILE = "aion2.dps.yaml"  # im Konfig-Ordner, benannt nach dem Modul
SETTINGS_HEADER = "AION-2-DPS – wird von der Web-UI überschrieben."

RETRY_S = 3
# Wie lange ohne neuen Schaden noch „im Kampf“, wenn return_after = 0
DEFAULT_IDLE_S = 30

Status = Literal["off", "no_meter", "overlay_off", "connecting", "bad_key", "connected",
                 "no_capture", "no_game", "no_caps", "capturing"]
LIVE = ("connected", "capturing")
# Phase des Mitschnitts (capture.py) → Status; alles andere heißt: er läuft
CAPTURE_STATUS: dict[str, Status] = {"no_binary": "no_capture", "no_game": "no_game", "no_caps": "no_caps",
                                     "crashed": "no_game", "starting": "connecting"}
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


SOURCES = {"capture": "Eigener Mitschnitt (deckbar-capture)", "auto": "A2Tools-Meter, Stream-Overlay (automatisch)",
           "manual": "A2Tools-Meter, Port und Schlüssel von Hand"}
ONLY_CAPTURE = {"show_if": {"source": ["capture"]}}
ONLY_MANUAL = {"show_if": {"source": ["manual"]}}


class DpsSettings(_Strict):
    enabled: bool = Field(True, json_schema_extra=HIDDEN)  # schaltet das Modul selbst (modules/dps.py)
    source: Literal["capture", "auto", "manual"] = Field(
        "capture", title="Quelle", description="Woher die Kampfdaten kommen", json_schema_extra={"labels": SOURCES})
    capture_bin: str = Field("", max_length=300, title="Programmpfad",
                             description="Leer = ~/.local/bin bzw. Build im Repo",
                             json_schema_extra=ONLY_CAPTURE | ADVANCED)
    port: int = Field(DEFAULT_PORT, ge=1024, le=65535, title="Port", description="Port des Stream-Overlays im Meter",
                      json_schema_extra=ONLY_MANUAL)
    key: str = Field("", max_length=128, title="Schlüssel", description="key=… aus der Overlay-URL des Meters",
                     json_schema_extra=SECRET | ONLY_MANUAL)
    return_after: int = Field(20, ge=0, le=600, title="Kampfende nach (s ohne Schaden)",
                              description="Danach gilt der Kampf als vorbei und die Leiste zeigt wieder die erste Seite")


class DpsFeed:
    def __init__(self, state: State, config_dir: Path, on_combat: CombatListener | None = None,
                 language: Callable[[], str] = lambda: "en") -> None:
        self.language = language  # Sprache der allgemeinen Einstellungen, gilt ab dem nächsten Start des Mitschnitts
        self.store = SettingsStore(config_dir / SETTINGS_FILE, DpsSettings, header=SETTINGS_HEADER)
        self.settings = self.store.value
        self.status: Status = "off"
        self.detail = ""
        self.port: int | None = None
        self.status_listeners: list[Callable[[], Awaitable[None]]] = []
        self.combat = CombatTracker(state, lambda: self.idle_after, on_combat)
        self._wake = asyncio.Event()
        self.capture = Capture(self._on_view, self._on_capture_change)

    # ------------------------------------------------------------ Einstellungen
    def save(self, settings: DpsSettings) -> None:
        self.store.save(settings)
        self.settings = settings

    @property
    def idle_after(self) -> int:
        return self.settings.return_after or DEFAULT_IDLE_S

    def info(self) -> dict:
        s = self.settings.model_dump()
        s["key"] = "•" * 8 if s["key"] else ""  # der Schlüssel verlässt den Daemon nicht
        # Port/Schlüssel des A2Tools-Meters nur, wenn es die Quelle ist (sonst bei jedem Statuswechsel
        # eine Datei lesen, für nichts)
        a2t = read_a2tools() if self.settings.source != "capture" else {}
        a2t.pop("key", None)
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
    async def _set_status(self, status: Status, detail: str = "") -> bool:
        """True, wenn sich etwas geändert hat (Zuhörer sind dann schon benachrichtigt)."""
        if (status, detail) == (self.status, self.detail):
            return False
        if status != self.status:
            log.info("DPS-Meter: %s%s", STATUS_TEXT[status], f" ({detail})" if detail else "")
        self.status, self.detail = status, detail
        if status not in LIVE:
            await self.combat.apply(None)
        for fn in self.status_listeners:
            await fn()
        return True

    async def _sleep(self, seconds: float) -> None:
        """Wartet, wacht aber sofort auf, wenn sich die Einstellungen ändern."""
        try:
            await asyncio.wait_for(self._wake.wait(), seconds)
        except TimeoutError:
            pass

    # ------------------------------------------------------------ Quelle: A2Tools-Meter
    def _target(self) -> tuple[int, str] | None:
        """Port und Schlüssel des Stream-Overlays; None = Meter nicht installiert, Port -1 = Overlay aus."""
        s = self.settings
        if s.source == "manual":
            return s.port, s.key
        a2t = read_a2tools()
        if not a2t["installed"]:
            return None
        if not a2t["enabled"] or not a2t["key"]:
            return -1, ""
        return a2t["port"], a2t["key"]

    async def _on_snapshot(self, snap: dict, first: bool) -> None:
        await self.combat.apply(compact(snap), baseline=first, fight=fight_view(snap))

    async def _meter_job(self, session: aiohttp.ClientSession) -> Awaitable[None] | None:
        """Die nächste Verbindung zum Meter; None, wenn es gerade nichts zu verbinden gibt (dann ist der
        Status gesetzt und es wurde schon gewartet)."""
        target = self._target()
        if target is None:
            await self._set_status("no_meter", "nicht installiert")
            await self._sleep(10)
            return None
        port, key = target
        if port < 0:
            await self._set_status("overlay_off")
            await self._sleep(5)
            return None
        self.port = port
        if self.status not in ("connected", "no_meter"):
            await self._set_status("connecting")
        return MeterStream(session, port, key, self._set_status, self._on_snapshot).run()

    # ------------------------------------------------------------ Quelle: eigener Mitschnitt
    async def _on_view(self, view: dict | None, first: bool) -> None:
        if self.status == "capturing":
            await self.combat.apply(compact(view) if view else None, baseline=first,
                                    fight=fight_view(view) if view else None)

    async def _on_capture_change(self) -> None:
        c = self.capture
        if self.settings.source != "capture" or not self.settings.enabled:
            return
        if c.phase in CAPTURE_STATUS:
            changed = await self._set_status(CAPTURE_STATUS[c.phase], c.error if c.phase == "crashed" else "")
        else:
            port = c.status.get("port")
            changed = await self._set_status("capturing", f"Spielserver-Port {port}" if port else "wartet auf Kampfdaten")
        if not changed:  # Ping/Port ändern sich ohne Statuswechsel
            for fn in self.status_listeners:
                await fn()

    # ------------------------------------------------------------ Ablauf
    async def watch(self) -> None:
        """Läuft, solange das Modul an ist: hält die gewählte Quelle am Laufen und startet sie neu, wenn sie
        endet oder sich die Einstellungen ändern."""
        idle = asyncio.ensure_future(self._idle_loop())
        timeout = aiohttp.ClientTimeout(total=None, connect=3, sock_read=READ_TIMEOUT_S)
        current: list[asyncio.Task] = []  # laufende Quelle, bei Abbruch mitbeenden
        try:
            async with aiohttp.ClientSession(timeout=timeout) as session:
                while True:
                    self._wake.clear()
                    job = await self._next_job(session)
                    if job is None:
                        continue
                    await self._until_wake(job, current)
                    if not self._wake.is_set():
                        await self._sleep(RETRY_S)
        finally:
            idle.cancel()
            # Modul aus: auch deckbar-capture beenden (asyncio.wait bricht die inneren Tasks nicht ab)
            for t in current:
                t.cancel()
            await asyncio.gather(*current, return_exceptions=True)

    async def _idle_loop(self) -> None:
        while True:
            await asyncio.sleep(1)
            await self.combat.check_idle()

    async def _next_job(self, session: aiohttp.ClientSession) -> Awaitable[None] | None:
        """Was als Nächstes läuft: der Mitschnitt, eine Verbindung zum Meter, oder nichts (ausgeschaltet)."""
        if not self.settings.enabled:
            self.port = None
            await self._set_status("off")
            await self._wake.wait()
            return None
        if self.settings.source == "capture":
            self.port = None
            return self.capture.run(self.settings.capture_bin, self.language())
        return await self._meter_job(session)

    async def _until_wake(self, job: Awaitable[None], current: list[asyncio.Task]) -> None:
        """Die Quelle laufen lassen, bis sie endet oder sich die Einstellungen ändern; dann sauber beenden."""
        task = asyncio.ensure_future(job)
        wake = asyncio.ensure_future(self._wake.wait())
        current[:] = [task, wake]
        await asyncio.wait({task, wake}, return_when=asyncio.FIRST_COMPLETED)
        for t in (task, wake):
            t.cancel()
        await asyncio.gather(task, return_exceptions=True)
