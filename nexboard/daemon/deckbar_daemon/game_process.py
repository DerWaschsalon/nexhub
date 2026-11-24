"""Läuft AION 2? Der Blick in /proc, wie ihn auch der Meter macht (AION2.exe unter Proton)."""
from __future__ import annotations

import os
import re
from pathlib import Path


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
