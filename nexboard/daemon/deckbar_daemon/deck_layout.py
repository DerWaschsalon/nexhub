"""layout.yaml der Leiste: das gültige Layout, seine Fassung fürs Gerät mit Hash und ein Fehlertext."""
from __future__ import annotations

import logging
from pathlib import Path
from typing import Any

import yaml
from nexcore.errors import invalid
from pydantic import ValidationError

from .config import Layout, Page, load_layout, save_layout

log = logging.getLogger(__name__)


def error_text(e: Exception) -> str:
    return invalid(e).message if isinstance(e, ValidationError) else str(e)


class DeckLayout:
    def __init__(self, path: Path) -> None:
        self.path = path
        self.error: str | None = None
        try:
            layout = load_layout(path)
        except (yaml.YAMLError, ValidationError) as e:
            # nicht abstürzen (systemd-Neustartschleife), sondern Fehler in der Web-UI zeigen
            self.error = error_text(e)
            log.error("layout.yaml ungültig, starte mit leerem Layout:\n%s", self.error)
            layout = Layout(pages=[Page(id="main", name="Fehler", items=[])])
        self.layout = layout
        self.payload = layout.device_payload()
        self._mtime = path.stat().st_mtime

    def set(self, layout: Layout, save: bool) -> None:
        if save:
            save_layout(self.path, layout)
            self._mtime = self.path.stat().st_mtime
        self.layout, self.payload, self.error = layout, layout.device_payload(), None

    def changed_on_disk(self) -> bool:
        """Hat jemand layout.yaml von Hand geändert? Merkt sich den neuen Stand."""
        try:
            mtime = self.path.stat().st_mtime
        except FileNotFoundError:
            return False
        if mtime == self._mtime:
            return False
        self._mtime = mtime
        return True

    def read(self) -> Layout:
        """layout.yaml lesen; ungültig: yaml.YAMLError oder ValidationError."""
        return load_layout(self.path)

    def json(self) -> dict[str, Any]:
        return self.layout.model_dump(mode="json", exclude_none=True)
