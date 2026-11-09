"""Einmaliger Umzug alter Einstellungen an ihren neuen Ort, vorher gesichert.

Läuft bei jedem Start, tut aber nur etwas, solange es noch etwas umzuziehen gibt: eine alte Datei ohne
neue, oder ein Schlüssel, der in ein anderes Modul gewandert ist.
"""
from __future__ import annotations

import logging
import shutil
from datetime import datetime
from pathlib import Path

import yaml
from nexcore import atomic_write

from . import bot, dps, runs
from .modules import deck

log = logging.getLogger(__name__)

# alte Datei → neue Datei (benannt nach dem Modul)
RENAMED = {"dps.yaml": dps.SETTINGS_FILE, "runs.yaml": runs.SETTINGS_FILE, "bot.yaml": bot.SETTINGS_FILE}
# (Datei, Schlüssel, neue Datei): Einstellung am falschen Ort, z. B. eine Leisten-Funktion unter DPS
MOVED_KEYS = [(dps.SETTINGS_FILE, "auto_page", deck.SETTINGS_FILE)]


class Backup:
    """Sicherung unter backup/vor-umzug-<Zeit>/, angelegt erst beim ersten Bedarf."""

    def __init__(self, config_dir: Path) -> None:
        self.config_dir = config_dir
        self.folder = config_dir / "backup" / f"vor-umzug-{datetime.now():%Y%m%d-%H%M%S}"

    def save(self, name: str) -> None:
        self.folder.mkdir(parents=True, exist_ok=True)
        if not (self.folder / name).exists():
            shutil.copy2(self.config_dir / name, self.folder / name)


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
    done = []
    for source, key, target in MOVED_KEYS:
        path = config_dir / source
        if (config_dir / target).exists() or not path.exists():
            continue
        data = yaml.safe_load(path.read_text()) or {}
        if not isinstance(data, dict) or key not in data:
            continue
        backup.save(source)
        atomic_write(config_dir / target, yaml.safe_dump({key: data.pop(key)}, allow_unicode=True))
        atomic_write(path, yaml.safe_dump(data, sort_keys=False, allow_unicode=True), path.stat().st_mode & 0o777)
        log.info("Einstellung %s umgezogen: %s → %s (Sicherung in %s)", key, source, target, backup.folder)
        done.append(f"{source}:{key}")
    return done


def migrate(config_dir: Path) -> list[str]:
    """Zieht um, was umzuziehen ist; zurück kommt, was umgezogen ist."""
    backup = Backup(config_dir)
    return _rename_files(config_dir, backup) + _move_keys(config_dir, backup)
