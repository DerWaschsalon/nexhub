"""Die Spiele der Reihe: woran man sie im Prozessbaum erkennt und wo ihr Client.txt liegt.

Unter Proton heißen PoE 1 und PoE 2 beide „PathOfExile…exe“. Unterscheiden lassen sie sich nur am
Installationsordner in der Befehlszeile („…\\Path of Exile\\“ gegen „…\\Path of Exile 2\\“). Der Prozessname
(comm) hilft nicht: unter Proton heißt das Spiel „Main“. Das Laufwerk ist je nach Start S: (Steam-Bibliothek)
oder Z:; den Linux-Ordner liefert deshalb der Arbeitsordner des Prozesses (/proc/<pid>/cwd).
"""
from __future__ import annotations

import os
import re
from dataclasses import dataclass
from pathlib import Path, PureWindowsPath

EXE_PREFIX = "pathofexile"  # PathOfExile.exe, PathOfExileSteam.exe, PathOfExile_x64Steam.exe …
STEAM_ROOTS = (".local/share/Steam", ".steam/steam")
LIBRARY_PATH = re.compile(r'"path"\s+"([^"]+)"')


@dataclass(frozen=True)
class RunningGame:
    install: Path | None  # Installationsordner, None = nicht aus der Befehlszeile ablesbar


@dataclass(frozen=True)
class PoeGame:
    id: str  # Präfix der Modul-IDs und Inhalt von game.started/game.stopped
    name: str
    folder: str  # Ordnername der Installation (Steam: steamapps/common/<folder>)

    def client_txt(self, install: Path) -> Path:
        return install / "logs" / "Client.txt"

    def is_game(self, cmdline: bytes) -> bool:
        """Startet die Befehlszeile das Spiel selbst (nicht Steam oder Proton, die es nur als Argument tragen)?"""
        exe = PureWindowsPath(cmdline.split(b"\0", 1)[0].decode(errors="replace"))
        name = exe.name.lower()
        return name.startswith(EXE_PREFIX) and name.endswith(".exe") and exe.parent.name == self.folder

    def find(self, proc: Path = Path("/proc")) -> RunningGame | None:
        """Den laufenden Spielprozess suchen (ein Blick in /proc)."""
        for pid in _pids(proc):
            try:
                cmdline = (proc / pid / "cmdline").read_bytes()
            except OSError:
                continue
            if self.is_game(cmdline):
                return RunningGame(self._install(proc / pid, cmdline))
        return None

    def _install(self, process: Path, cmdline: bytes) -> Path | None:
        """Installationsordner: Arbeitsordner des Spiels, sonst der Pfad auf Z: aus der Befehlszeile."""
        try:
            cwd = (process / "cwd").readlink()
        except OSError:
            cwd = None
        if cwd and cwd.name == self.folder:
            return cwd
        return linux_path(PureWindowsPath(cmdline.split(b"\0", 1)[0].decode(errors="replace")).parent)

    def steam_client_txt(self, home: Path | None = None) -> Path | None:
        """Client.txt aus den Steam-Bibliotheken, wenn das Spiel gerade nicht läuft."""
        for library in steam_libraries(home or Path.home()):
            path = self.client_txt(library / "steamapps" / "common" / self.folder)
            if path.is_file():
                return path
        return None


def linux_path(path: PureWindowsPath) -> Path | None:
    """Z:\\home\\… ist unter Wine das Linux-Wurzelverzeichnis; andere Laufwerke liegen im Prefix."""
    if path.drive.upper() != "Z:":
        return None
    return Path("/", *path.parts[1:])


def steam_libraries(home: Path) -> list[Path]:
    out: list[Path] = []
    for root in STEAM_ROOTS:
        try:
            text = (home / root / "steamapps" / "libraryfolders.vdf").read_text(errors="replace")
        except OSError:
            continue
        for found in LIBRARY_PATH.findall(text):
            library = Path(found)
            if library not in out:
                out.append(library)
    return out


def _pids(proc: Path) -> list[str]:
    try:
        return [e.name for e in os.scandir(proc) if e.name.isdigit()]
    except OSError:
        return []


POE1 = PoeGame("poe1", "Path of Exile", "Path of Exile")
POE2 = PoeGame("poe2", "Path of Exile 2", "Path of Exile 2")
