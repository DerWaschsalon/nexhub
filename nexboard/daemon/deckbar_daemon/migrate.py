"""Einmaliger Umzug alter Einstellungsdateien auf die Namen ihrer Module, vorher gesichert.

Läuft bei jedem Start, tut aber nur etwas, solange eine alte Datei da ist und die neue noch nicht.
"""
from __future__ import annotations

import logging
import shutil
from datetime import datetime
from pathlib import Path

from . import bot, dps, runs

log = logging.getLogger(__name__)

RENAMED = {"dps.yaml": dps.SETTINGS_FILE, "runs.yaml": runs.SETTINGS_FILE, "bot.yaml": bot.SETTINGS_FILE}


def migrate(config_dir: Path) -> list[str]:
    """Benennt um, was umzuziehen ist; zurück kommen die alten Namen. Sicherung unter backup/."""
    todo = [(old, new) for old, new in RENAMED.items()
            if (config_dir / old).exists() and not (config_dir / new).exists()]
    if not todo:
        return []
    backup = config_dir / "backup" / f"vor-umzug-{datetime.now():%Y%m%d-%H%M%S}"
    backup.mkdir(parents=True, exist_ok=True)
    for old, new in todo:
        shutil.copy2(config_dir / old, backup / old)
        (config_dir / old).rename(config_dir / new)
        log.info("Einstellungen umgezogen: %s → %s (Sicherung in %s)", old, new, backup)
    return [old for old, _ in todo]
