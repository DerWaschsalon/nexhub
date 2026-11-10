"""Einmaliger Umzug alter Einstellungen an ihren neuen Ort, vorher gesichert.

Läuft bei jedem Start, tut aber nur etwas, solange es noch etwas umzuziehen gibt: eine alte Datei ohne
neue, ein Schlüssel, der in ein anderes Modul gewandert ist, oder eine Liste, die jetzt ein Modul führt.
"""
from __future__ import annotations

import json
import logging
import shutil
from datetime import datetime
from pathlib import Path

import yaml
from nexcore import atomic_write
from nexproto.termine import TERMINE

from . import dps, runs, schedule
from .modules import deck

log = logging.getLogger(__name__)

# alte Datei → neue Datei (benannt nach dem Modul)
RENAMED = {"dps.yaml": dps.SETTINGS_FILE, "runs.yaml": runs.SETTINGS_FILE}
# (Datei, Schlüssel, neue Datei, neuer Schlüssel): Einstellung am falschen Ort, z. B. eine Leisten-Funktion
# unter DPS oder die Sprache, die jetzt für alles gilt
MOVED_KEYS = [(dps.SETTINGS_FILE, "auto_page", deck.SETTINGS_FILE, "auto_page"),
              (dps.SETTINGS_FILE, "lang", "config.yaml", "language")]
OVERLAY_LAYOUT = Path("overlay") / "layout.json"
# Voreinstellungen der alten Event-Timer im Overlay; sie stehen jetzt als feste Termine in nexproto
FORMER_DEFAULT_EVENTS = {"Shugo-Festival", "Spacetime Rift", "Täglicher Reset", "Wöchentlicher Reset"}


class Backup:
    """Sicherung unter backup/vor-umzug-<Zeit>/, angelegt erst beim ersten Bedarf."""

    def __init__(self, config_dir: Path) -> None:
        self.config_dir = config_dir
        self.folder = config_dir / "backup" / f"vor-umzug-{datetime.now():%Y%m%d-%H%M%S}"

    def save(self, name: str | Path) -> None:
        target = self.folder / name
        target.parent.mkdir(parents=True, exist_ok=True)
        if not target.exists():
            shutil.copy2(self.config_dir / name, target)


def _read_yaml(path: Path) -> dict:
    if not path.exists():
        return {}
    data = yaml.safe_load(path.read_text()) or {}
    return data if isinstance(data, dict) else {}


def _write_yaml(path: Path, data: dict) -> None:
    """Rechte bleiben (config.yaml enthält das Geräte-Token); neue Dateien sind für alle lesbar."""
    mode = path.stat().st_mode & 0o777 if path.exists() else 0o644
    atomic_write(path, yaml.safe_dump(data, sort_keys=False, allow_unicode=True), mode)


def _rename_files(config_dir: Path, backup: Backup) -> list[str]:
    done = []
    for old, new in RENAMED.items():
        if (config_dir / old).exists() and not (config_dir / new).exists():
            backup.save(old)
            (config_dir / old).rename(config_dir / new)
            log.info("Einstellungen umgezogen: %s → %s (Sicherung in %s)", old, new, backup.folder)
            done.append(old)
    return done


def _move_keys(config_dir: Path, backup: Backup) -> list[str]:
    """Steht der neue Schlüssel schon im Ziel, gilt der; der alte fällt dann nur weg."""
    done = []
    for source, key, target, new_key in MOVED_KEYS:
        data = _read_yaml(config_dir / source)
        if key not in data:
            continue
        backup.save(source)
        value = data.pop(key)
        goal = _read_yaml(config_dir / target)
        if new_key not in goal:
            if (config_dir / target).exists():
                backup.save(target)
            _write_yaml(config_dir / target, {**goal, new_key: value})
        _write_yaml(config_dir / source, data)
        log.info("Einstellung %s umgezogen: %s → %s:%s (Sicherung in %s)", key, source, target, new_key, backup.folder)
        done.append(f"{source}:{key}")
    return done


def _adopt_character_name(config_dir: Path, backup: Backup, radar_settings: Path | None) -> list[str]:
    """Der Charaktername stand im Radar; jetzt gilt der aus den allgemeinen Einstellungen für alles."""
    if not radar_settings or not radar_settings.exists() or "character_name" in _read_yaml(config_dir / "config.yaml"):
        return []
    try:
        name = json.loads(radar_settings.read_text()).get("name") or ""
    except (OSError, ValueError, AttributeError):
        return []
    if not name or not (config_dir / "config.yaml").exists():
        return []
    backup.save("config.yaml")
    _write_yaml(config_dir / "config.yaml", {**_read_yaml(config_dir / "config.yaml"), "character_name": name})
    log.info("Charaktername aus %s übernommen (Sicherung in %s)", radar_settings, backup.folder)
    return ["character_name"]


def _move_timer_events(config_dir: Path, backup: Backup) -> list[str]:
    """Event-Timer des Overlays → Modul Termine: eigene Ereignisse bleiben, die alten und neuen
    Voreinstellungen fallen weg (die festen Termine kommen jetzt aus nexproto)."""
    path = config_dir / OVERLAY_LAYOUT
    if (config_dir / schedule.SETTINGS_FILE).exists() or not path.exists():
        return []
    try:
        layout = json.loads(path.read_text())
        events = layout["widgets"]["timers"].pop("events")
    except (OSError, ValueError, KeyError, TypeError, AttributeError):
        return []
    builtin = FORMER_DEFAULT_EVENTS | {name for name, *_ in TERMINE}
    own = [e for e in events if isinstance(e, dict) and e.get("name") not in builtin]
    backup.save(OVERLAY_LAYOUT)
    _write_yaml(config_dir / schedule.SETTINGS_FILE, {"events": own})
    atomic_write(path, json.dumps(layout, ensure_ascii=False, indent=1) + "\n")
    log.info("Event-Timer umgezogen: %d eigene Ereignisse nach %s (Sicherung in %s)",
             len(own), schedule.SETTINGS_FILE, backup.folder)
    return [f"{OVERLAY_LAYOUT}:events"]


def migrate(config_dir: Path, radar_settings: Path | None = None) -> list[str]:
    """Zieht um, was umzuziehen ist; zurück kommt, was umgezogen ist. radar_settings: Datei des Radars
    (nur beim Daemon mit der echten Konfiguration, Testinstanzen lesen sie nicht)."""
    backup = Backup(config_dir)
    return (_rename_files(config_dir, backup) + _move_keys(config_dir, backup)
            + _adopt_character_name(config_dir, backup, radar_settings) + _move_timer_events(config_dir, backup))
