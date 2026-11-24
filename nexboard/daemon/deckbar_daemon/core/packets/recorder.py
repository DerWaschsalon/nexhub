"""Aufnahme für den Lernmodus: ein eigenes tcpdump schreibt den Server-Verkehr als pcap in den Datenordner.
Die Aufnahmen spielt der Goldtest ab, und die Werkzeuge werten sie aus."""
from __future__ import annotations

import logging
import subprocess
from datetime import datetime
from pathlib import Path

from .tcp import start_tcpdump

log = logging.getLogger(__name__)

RECORDINGS = Path.home() / ".local" / "share" / "aion2-radar" / "mitschnitte"  # nie ins Repo


class Recorder:
    def __init__(self) -> None:
        self._process: subprocess.Popen | None = None

    @property
    def recording(self) -> bool:
        return self._process is not None

    def start(self, name: str = "dungeon") -> None:
        self.stop()
        RECORDINGS.mkdir(parents=True, exist_ok=True)
        file = RECORDINGS / f"{name.replace(' ', '_')}-{datetime.now():%Y%m%d-%H%M}.pcap"
        self._process = start_tcpdump(file=str(file))
        log.info("Aufnahme läuft: %s", file.name)

    def stop(self) -> None:
        if self._process:
            self._process.terminate()
            self._process = None
            log.info("Aufnahme beendet")
