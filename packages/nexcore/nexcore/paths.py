"""Ablageorte nach XDG und atomares Schreiben: eine Stelle statt fünf Kopien im Daemon."""
from __future__ import annotations

import os
import tempfile
from dataclasses import dataclass
from pathlib import Path


def _xdg(variable: str, fallback: str) -> Path:
    return Path(os.environ.get(variable) or Path.home() / fallback)


@dataclass(frozen=True)
class Paths:
    """Ordner eines Programms (z. B. "deckbar") unter den XDG-Basisordnern."""
    app: str

    @property
    def config(self) -> Path:
        return _xdg("XDG_CONFIG_HOME", ".config") / self.app

    @property
    def data(self) -> Path:
        return _xdg("XDG_DATA_HOME", ".local/share") / self.app

    @property
    def cache(self) -> Path:
        return _xdg("XDG_CACHE_HOME", ".cache") / self.app

    @property
    def runtime(self) -> Path:
        base = os.environ.get("XDG_RUNTIME_DIR") or tempfile.gettempdir()
        return Path(base) / self.app


def atomic_write(path: Path, text: str, mode: int = 0o644) -> None:
    """Erst ganz in eine Nachbardatei schreiben, dann ersetzen: nie eine halbe Datei, auch beim Absturz."""
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp = tempfile.mkstemp(dir=path.parent, prefix=f".{path.name}.")
    with os.fdopen(fd, "w") as f:
        f.write(text)
    os.chmod(tmp, mode)
    os.replace(tmp, path)
