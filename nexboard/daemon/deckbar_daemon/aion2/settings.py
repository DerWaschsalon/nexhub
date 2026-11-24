"""Einstellungen des Radars (~/.config/aion2-radar.json) über den Standardwerten aus data/defaults.json.

Alle Teile halten dasselbe dict; `reload()` füllt es nach einer Änderung auf der NexBoard-Seite neu. Mit der
Zerlegung in Module bekommt jedes Modul seine Einstellungen über den Daemon (Umbauschritt 7, Teil Module).
"""
from __future__ import annotations

import json
from pathlib import Path

from .gamedata import load_data

FILE = Path.home() / ".config" / "aion2-radar.json"
DEFAULTS: dict = load_data("defaults.json")

_settings: dict | None = None


def with_defaults(own: dict) -> dict:
    """Eigene Einstellungen über die Standardwerte legen. warnton einzeln, damit neue Warnungen ihren
    Standard-Ton auch dann bekommen, wenn schon eigene Töne gespeichert sind."""
    return {**DEFAULTS, **own, "warnton": {**DEFAULTS["warnton"], **own.get("warnton", {})}}


def read_file() -> dict:
    try:
        content = json.loads(FILE.read_text())
    except (OSError, ValueError):
        return {}
    return content if isinstance(content, dict) else {}


def settings() -> dict:
    """Das gemeinsame Einstellungs-dict (nur einmal gelesen)."""
    global _settings
    if _settings is None:
        _settings = with_defaults(read_file())
    return _settings


def reload() -> dict:
    """Datei neu lesen; ändert dasselbe dict, das alle Teile halten."""
    current = settings()
    fresh = with_defaults(read_file())
    current.clear()
    current.update(fresh)
    return current


def use(values: dict | None) -> None:
    """Für Tests und Werkzeuge: diese Einstellungen statt der Datei (None = wieder die Datei)."""
    global _settings
    _settings = values
