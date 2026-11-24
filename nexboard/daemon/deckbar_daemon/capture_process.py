"""Das Programm `deckbar-capture` als Prozess: finden, starten, Zeilen schreiben, sauber beenden."""
from __future__ import annotations

import asyncio
import logging
import os
import shutil
from pathlib import Path

from .capture_protocol import MAX_LINE

log = logging.getLogger(__name__)

BINARY = "deckbar-capture"
STOP_WAIT_S = 10  # nach geschlossener Eingabe, dann SIGTERM
CLEAN_EXITS = (0, None, -15)  # beendet, noch am Laufen, SIGTERM von uns


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


class CaptureProcess:
    def __init__(self) -> None:
        self._proc: asyncio.subprocess.Process | None = None

    @property
    def running(self) -> bool:
        return self._proc is not None and self._proc.returncode is None

    @property
    def stdout(self) -> asyncio.StreamReader:
        assert self._proc and self._proc.stdout
        return self._proc.stdout

    @property
    def crashed(self) -> int | None:
        """Exit-Code, wenn das Programm von selbst mit einem Fehler geendet hat."""
        code = self._proc.returncode if self._proc else None
        return None if code in CLEAN_EXITS else code

    async def start(self, binary: Path, lang: str, interval_ms: int) -> None:
        """OSError, wenn sich das Programm nicht starten lässt."""
        args = [str(binary), "--history-dir", str(history_root()), "--lang", lang, "--interval-ms", str(interval_ms)]
        self._proc = await asyncio.create_subprocess_exec(
            *args, stdin=asyncio.subprocess.PIPE, stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE, limit=MAX_LINE)
        log.info("%s gestartet (PID %s)", BINARY, self._proc.pid)

    async def send(self, line: bytes) -> None:
        proc = self._proc
        if not self.running or not proc or not proc.stdin:
            raise RuntimeError(f"{BINARY} läuft nicht")
        proc.stdin.write(line)
        await proc.stdin.drain()

    async def stop(self) -> None:
        """Eingabe schließen: Das Programm speichert die laufenden Kämpfe und beendet sich."""
        proc = self._proc
        if not proc or proc.returncode is not None:
            return
        try:
            if proc.stdin:
                proc.stdin.close()
            await asyncio.wait_for(proc.wait(), STOP_WAIT_S)
        except (TimeoutError, ProcessLookupError):
            try:
                proc.terminate()
                await asyncio.wait_for(proc.wait(), STOP_WAIT_S)
            except (TimeoutError, ProcessLookupError):
                proc.kill()
        except OSError:
            pass

    def forget(self) -> None:
        self._proc = None

    async def log_stderr(self) -> None:
        assert self._proc and self._proc.stderr
        while raw := await self._proc.stderr.readline():
            line = raw.decode(errors="replace").rstrip()
            level = logging.WARNING if " WARN " in line or " ERROR " in line else logging.DEBUG
            log.log(level, "%s: %s", BINARY, line)
