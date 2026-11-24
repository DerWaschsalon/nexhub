"""AION-2-Mitschnitt per `deckbar-capture` (Ordner capture/ im Repo, Kern des A2Tools DPS Meter).

Läuft AION 2 (Prozess AION2.exe unter Proton), startet der Daemon das Programm (capture_process.py) und
liest dessen Zeilen-JSON (capture_protocol.py). Endet das Spiel, schließt der Daemon nach STOP_AFTER_S die
Eingabe des Programms. Es speichert dann die laufenden Kämpfe und beendet sich.
"""
from __future__ import annotations

import asyncio
import logging
from pathlib import Path
from typing import Any, Awaitable, Callable, Literal

from .capture_process import BINARY, CaptureProcess, find_binary, history_root, repo_binary
from .capture_protocol import Requests, parse
from .game_process import aion2_running

log = logging.getLogger(__name__)

DEFAULT_INTERVAL_MS = 500  # Standard von deckbar-capture
GAME_POLL_S = 5
STOP_AFTER_S = 30   # Spiel weg: so lange weiterlaufen lassen (Absturz mit Neustart, Ladebildschirm)
PING_STEP_MS = 5
PLUGIN_EVENTS = ("plugin_frame", "plugin_character", "plugin_feed")

Phase = Literal["no_binary", "no_game", "starting", "running", "no_caps", "crashed"]
ViewListener = Callable[[dict | None, bool], Awaitable[None]]  # (view oder None, erster nach Start)


def _without_ping(status: dict) -> dict:
    return {k: v for k, v in status.items() if k != "ping"}


class Capture:
    """Hält deckbar-capture am Laufen, solange das Spiel läuft, und verteilt, was es meldet."""

    def __init__(self, on_view: ViewListener, on_change: Callable[[], Awaitable[None]],
                 on_fights: Callable[[list[str]], Awaitable[None]] | None = None) -> None:
        self.on_view = on_view
        self.on_change = on_change
        self.on_fights = on_fights
        self.phase: Phase = "no_game"
        self.binary: Path | None = None
        self.hello: dict[str, Any] = {}
        self.status: dict[str, Any] = {}
        self.error = ""
        self.game_running = aion2_running  # austauschbar für Tests
        self.game: bool | None = None  # letzter Blick auf /proc (None = noch keiner bzw. ohne Programm)
        # Takt der DPS-Ansicht; die A2-Oberfläche setzt ihn aus den Meter-Einstellungen (a2ui.py)
        self.interval_ms = DEFAULT_INTERVAL_MS
        # Volle DpsData (Skills je Spieler) nur, solange jemand sie braucht (Overlay, meter_events.py)
        self.full = False
        self.data_listeners: list[Callable[[str, Any], Awaitable[None]]] = []  # (Ereignis, Inhalt)
        self.process = CaptureProcess()
        self.requests = Requests()

    def info(self) -> dict:
        return {
            "phase": self.phase,
            "binary": str(self.binary) if self.binary else None,
            "repo_binary": str(repo_binary()),
            "cap_net_raw": self.hello.get("cap_net_raw"),
            "version": self.hello.get("version"),
            "parser": self.hello.get("parser"),
            "history_dir": str(history_root() / "history"),
            "port": self.status.get("port"),
            "ping": self.status.get("ping"),
            "error": self.error,
        }

    async def _set(self, phase: Phase, error: str = "") -> None:
        if (phase, error) != (self.phase, self.error):
            self.phase, self.error = phase, error
            await self.on_change()

    # ------------------------------------------------------------ Lebenszyklus
    async def run(self, configured_binary: str = "", lang: str = "en") -> None:
        """Bis zum Abbruch: auf das Spiel warten, Programm starten, mit dem Spiel beenden."""
        try:
            while True:
                self.binary = find_binary(configured_binary)
                if self.binary is None:
                    self.game = None
                    await self._set("no_binary", f"{BINARY} nicht gefunden")
                    await asyncio.sleep(GAME_POLL_S)
                    continue
                self.game = await asyncio.to_thread(self.game_running)
                if not self.game:
                    await self._set("no_game")
                    await asyncio.sleep(GAME_POLL_S)
                    continue
                await self._run_once(self.binary, lang)
        finally:
            self.game = None
            await self.process.stop()

    async def _run_once(self, binary: Path, lang: str) -> None:
        await self._set("starting")
        self.hello, self.status = {}, {}
        try:
            await self.process.start(binary, lang, self.interval_ms)
        except OSError as e:
            await self._set("crashed", str(e))
            await asyncio.sleep(GAME_POLL_S)
            return
        reader = asyncio.ensure_future(self._read(self.process))
        errors = asyncio.ensure_future(self.process.log_stderr())
        watcher = asyncio.ensure_future(self._watch_game())
        try:
            await asyncio.wait({reader, watcher}, return_when=asyncio.FIRST_COMPLETED)
        finally:
            watcher.cancel()
            await self.process.stop()
            reader.cancel()
            errors.cancel()
            self.requests.cancel_all()
            await self.on_view(None, False)
        code = self.process.crashed
        self.process.forget()
        if code is not None:
            await self._set("crashed", f"Exit-Code {code}")
            await asyncio.sleep(GAME_POLL_S)

    async def _watch_game(self) -> None:
        gone = 0.0
        while True:
            await asyncio.sleep(GAME_POLL_S)
            # deckbar-capture sucht das Spiel selbst (Status-Feld game, bei jeder Änderung gemeldet):
            # dann kein zweiter /proc-Scan
            game = self.status.get("game")
            self.game = game if isinstance(game, bool) else await asyncio.to_thread(self.game_running)
            if self.game:
                gone = 0
                continue
            gone += GAME_POLL_S
            if gone >= STOP_AFTER_S:
                log.info("AION 2 beendet, stoppe %s", BINARY)
                return

    # ------------------------------------------------------------ Ausgabe
    async def _read(self, proc: Any) -> None:
        """Zeilen von proc.stdout verteilen, bis das Programm endet."""
        first = True
        while True:
            try:
                raw = await proc.stdout.readline()
            except ValueError:  # Zeile über MAX_LINE
                log.warning("%s: Zeile zu lang, verworfen", BINARY)
                continue
            if not raw:
                return
            match parse(raw):
                case ("dps_data", text):
                    await self._notify("dps_data", text)
                case ("dps", {"view": dict(view)}):
                    await self.on_view(view, first)
                    first = False
                case ("status", msg):
                    await self._on_status(msg)
                case ("hello", msg):
                    await self._on_hello(msg)
                case ("fights_saved", msg):
                    ids = [str(i) for i in msg.get("ids") or []]
                    if self.on_fights:
                        await self.on_fights(ids)
                    await self._notify("fights_saved", ids)
                case (str(kind), msg) if kind in PLUGIN_EVENTS:
                    await self._notify(kind, msg)
                case ("reply", msg):
                    self.requests.reply(msg)

    async def _on_status(self, msg: dict) -> None:
        ping = msg.get("ping")
        if ping != self.status.get("ping"):
            await self._notify("ping", ping)
        old, self.status = self.status, msg
        # deckbar-capture meldet jede Ping-Änderung (alle 2 s); Web-UI und Dashboard nur bei
        # spürbarer Änderung (≥ PING_STEP_MS) oder wenn sich sonst etwas tut
        p0 = old.get("ping")
        small = isinstance(p0, (int, float)) and isinstance(ping, (int, float)) and abs(ping - p0) < PING_STEP_MS
        if _without_ping(old) == _without_ping(msg) and (small or p0 == ping):
            self.status = {**msg, "ping": p0}  # Bezugswert bleibt der zuletzt gezeigte
        else:
            await self.on_change()

    async def _on_hello(self, msg: dict) -> None:
        self.hello = msg
        if "dps_data" not in (msg.get("features") or []):
            log.warning("%s ist veraltet, Meter-Daten und Boss-Effekte fehlen: capture/build.sh --install", BINARY)
        if self.full:
            asyncio.ensure_future(self._send_view())
        if msg.get("cap_net_raw"):
            await self._set("running")
        else:
            await self._set("no_caps", "ohne cap_net_raw kein Mitschnitt")
        await self._notify("hello", msg)

    async def _notify(self, event: str, payload: Any) -> None:
        for fn in self.data_listeners:
            try:
                await fn(event, payload)
            except Exception:  # ein kaputter Zuhörer darf den Mitschnitt nicht anhalten
                log.exception("Zuhörer für %s", event)

    async def set_full(self, on: bool) -> None:
        if on != self.full:
            self.full = on
            if self.running:
                await self._send_view()

    async def _send_view(self) -> None:
        try:
            await self.request("view", full=self.full)
        except (RuntimeError, TimeoutError, OSError) as e:
            log.debug("view: %s", e)

    # ------------------------------------------------------------ Befehle
    @property
    def running(self) -> bool:
        return self.process.running

    async def request(self, cmd: str, timeout: float = 5, **args: Any) -> Any:
        """Befehl an das Programm (reset, target_mode, details, history …), wartet auf die Antwort."""
        rid, reply, line = self.requests.new(cmd, args)
        try:
            await self.process.send(line)
            return await asyncio.wait_for(reply, timeout)
        finally:
            self.requests.drop(rid)
