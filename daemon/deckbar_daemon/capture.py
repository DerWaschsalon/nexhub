"""AION-2-Mitschnitt per `deckbar-capture` (Ordner capture/ im Repo, Kern des A2Tools DPS Meter).

Läuft AION 2 (Prozess AION2.exe unter Proton), startet der Daemon das Programm und liest dessen
Zeilen-JSON (Format siehe capture/src/main.rs):

    {"type":"hello","cap_net_raw":true,…}         einmal beim Start
    {"type":"dps","view":{"target":…,"timeMs":…,"hp":…,"rows":[…]}}   bei jeder Änderung
    {"type":"status","port":…,"ping":…,"dungeon":…}                   bei jeder Änderung
    {"type":"fights_saved","ids":[…]}             Kampf-History geschrieben
    {"type":"reply","id":…,"ok":…,"result":…}     Antwort auf request()

Endet das Spiel, schließt der Daemon nach STOP_AFTER_S die Eingabe des Programms. Es speichert
dann die laufenden Kämpfe und beendet sich.
"""
from __future__ import annotations

import asyncio
import itertools
import json
import logging
import os
import re
import shutil
from pathlib import Path
from typing import Any, Awaitable, Callable, Literal

log = logging.getLogger(__name__)

BINARY = "deckbar-capture"
GAME_POLL_S = 5
STOP_AFTER_S = 30   # Spiel weg: so lange weiterlaufen lassen (Absturz mit Neustart, Ladebildschirm)
STOP_WAIT_S = 10    # nach geschlossener Eingabe, dann SIGTERM
MAX_LINE = 4 * 1024 * 1024  # volle DpsData mit allen Skills

Phase = Literal["no_binary", "no_game", "starting", "running", "no_caps", "crashed"]


def repo_binary() -> Path:
    return Path(__file__).resolve().parents[2] / "capture" / "target" / "release" / BINARY


def find_binary(configured: str = "") -> Path | None:
    """Fester Pfad aus den Einstellungen, sonst PATH bzw. ~/.local/bin (`build.sh --install`, mit
    cap_net_raw), sonst der Build im Repo."""
    if configured:
        p = Path(configured).expanduser()
        return p if p.is_file() else None
    found = shutil.which(BINARY)
    if found:
        return Path(found)
    for p in (Path.home() / ".local" / "bin" / BINARY, repo_binary()):
        if p.is_file():
            return p
    return None


def history_root() -> Path:
    """Dort schreibt deckbar-capture `history/<id>.json` (Format des A2Tools-Meters)."""
    base = os.environ.get("XDG_DATA_HOME") or str(Path.home() / ".local" / "share")
    return Path(base) / "deckbar" / "aion2"


def is_aion2_process(comm: str, cmdline: bytes) -> bool:
    """Wie `platform::procfs::is_aion2_process` im Meter: Name des Prozesses oder argv[0]."""
    def is_game(name: str) -> bool:
        return name.strip().lower() == "aion2.exe"

    if is_game(comm):
        return True
    argv0 = cmdline.split(b"\0", 1)[0].decode(errors="replace")
    return is_game(re.split(r"[/\\]", argv0)[-1])


def aion2_running(proc: Path = Path("/proc")) -> bool:
    try:
        entries = list(os.scandir(proc))
    except OSError:
        return False
    for e in entries:
        if not e.name.isdigit():
            continue
        try:
            comm = (proc / e.name / "comm").read_text()
            if is_aion2_process(comm, b""):
                return True
            if "wine" in comm.lower() or comm.strip().lower().startswith("aion"):
                if is_aion2_process("", (proc / e.name / "cmdline").read_bytes()):
                    return True
        except OSError:
            continue
    return False


ViewListener = Callable[[dict | None, bool], Awaitable[None]]  # (view oder None, erster nach Start)


class Capture:
    """Hält deckbar-capture am Laufen, solange das Spiel läuft."""

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
        # Volle DpsData (Skills je Spieler) nur, solange jemand sie braucht (Overlay, a2ui.py)
        self.full = False
        self.data_listeners: list[Callable[[str, Any], Awaitable[None]]] = []  # (Ereignis, Inhalt)
        self._proc: asyncio.subprocess.Process | None = None
        self._pending: dict[int, asyncio.Future] = {}
        self._ids = itertools.count(1)

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
                    await self._set("no_binary", f"{BINARY} nicht gefunden")
                    await asyncio.sleep(GAME_POLL_S)
                    continue
                if not await asyncio.to_thread(self.game_running):
                    await self._set("no_game")
                    await asyncio.sleep(GAME_POLL_S)
                    continue
                await self._run_once(lang)
        finally:
            await self._stop()

    async def _run_once(self, lang: str) -> None:
        await self._set("starting")
        self.hello, self.status = {}, {}
        args = [str(self.binary), "--history-dir", str(history_root()), "--lang", lang]
        try:
            self._proc = await asyncio.create_subprocess_exec(
                *args, stdin=asyncio.subprocess.PIPE, stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE, limit=MAX_LINE)
        except OSError as e:
            await self._set("crashed", str(e))
            await asyncio.sleep(GAME_POLL_S)
            return
        log.info("%s gestartet (PID %s)", BINARY, self._proc.pid)
        reader = asyncio.ensure_future(self._read(self._proc))
        errors = asyncio.ensure_future(self._log_stderr(self._proc))
        watcher = asyncio.ensure_future(self._watch_game())
        try:
            await asyncio.wait({reader, watcher}, return_when=asyncio.FIRST_COMPLETED)
        finally:
            watcher.cancel()
            await self._stop()
            reader.cancel()
            errors.cancel()
            for fut in self._pending.values():
                fut.cancel()
            self._pending.clear()
            await self.on_view(None, False)
        code = self._proc.returncode if self._proc else None
        self._proc = None
        if code not in (0, None, -15):
            await self._set("crashed", f"Exit-Code {code}")
            await asyncio.sleep(GAME_POLL_S)

    async def _watch_game(self) -> None:
        gone = 0.0
        while True:
            await asyncio.sleep(GAME_POLL_S)
            if await asyncio.to_thread(self.game_running):
                gone = 0
                continue
            gone += GAME_POLL_S
            if gone >= STOP_AFTER_S:
                log.info("AION 2 beendet, stoppe %s", BINARY)
                return

    async def _stop(self) -> None:
        proc = self._proc
        if not proc or proc.returncode is not None:
            return
        try:
            if proc.stdin:
                proc.stdin.close()  # Programm speichert und beendet sich
            await asyncio.wait_for(proc.wait(), STOP_WAIT_S)
        except (TimeoutError, ProcessLookupError):
            try:
                proc.terminate()
                await asyncio.wait_for(proc.wait(), STOP_WAIT_S)
            except (TimeoutError, ProcessLookupError):
                proc.kill()
        except OSError:
            pass

    # ------------------------------------------------------------ Ausgabe
    async def _read(self, proc: asyncio.subprocess.Process) -> None:
        assert proc.stdout
        first = True
        while True:
            try:
                raw = await proc.stdout.readline()
            except ValueError:  # Zeile über MAX_LINE
                log.warning("%s: Zeile zu lang, verworfen", BINARY)
                continue
            if not raw:
                return
            try:
                msg = json.loads(raw)
            except ValueError:
                continue
            if not isinstance(msg, dict):
                continue
            t = msg.get("type")
            if t == "dps" and isinstance(msg.get("view"), dict):
                await self.on_view(msg["view"], first)
                first = False
                if "data" in msg:
                    await self._notify("dps", msg["data"])
            elif t == "status":
                ping = msg.get("ping")
                if ping != self.status.get("ping"):
                    await self._notify("ping", ping)
                self.status = msg
                await self.on_change()
            elif t == "hello":
                self.hello = msg
                if self.full:
                    asyncio.ensure_future(self._send_view())
                if msg.get("cap_net_raw"):
                    await self._set("running")
                else:
                    await self._set("no_caps", "ohne cap_net_raw kein Mitschnitt")
            elif t == "fights_saved":
                ids = [str(i) for i in msg.get("ids") or []]
                if self.on_fights:
                    await self.on_fights(ids)
                await self._notify("fights_saved", ids)
            elif t == "reply":
                fut = self._pending.pop(msg.get("id"), None)
                if fut and not fut.done():
                    if msg.get("ok"):
                        fut.set_result(msg.get("result"))
                    else:
                        fut.set_exception(RuntimeError(str(msg.get("error"))))

    async def _log_stderr(self, proc: asyncio.subprocess.Process) -> None:
        assert proc.stderr
        while raw := await proc.stderr.readline():
            line = raw.decode(errors="replace").rstrip()
            level = logging.WARNING if " WARN " in line or " ERROR " in line else logging.DEBUG
            log.log(level, "%s: %s", BINARY, line)

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
        return self._proc is not None and self._proc.returncode is None

    async def request(self, cmd: str, timeout: float = 5, **args: Any) -> Any:
        """Befehl an das Programm (reset, target_mode, details, history …), wartet auf die Antwort."""
        proc = self._proc
        if not self.running or not proc or not proc.stdin:
            raise RuntimeError(f"{BINARY} läuft nicht")
        rid = next(self._ids)
        fut: asyncio.Future = asyncio.get_running_loop().create_future()
        self._pending[rid] = fut
        proc.stdin.write((json.dumps({"id": rid, "cmd": cmd, **args}) + "\n").encode())
        await proc.stdin.drain()
        try:
            return await asyncio.wait_for(fut, timeout)
        finally:
            self._pending.pop(rid, None)
