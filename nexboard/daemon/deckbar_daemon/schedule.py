"""Termine: die festen Termine der Server (nexproto.termine) und eigene Ereignisse in einer Liste.

Dieselbe Liste zeigen die Seite „Termine“ der Web-UI und das Termine-Widget im Overlay. Gerechnet wird
nur hier (mit nexproto.termine); Web-UI und Overlay zählen bloß bis zu den gelieferten Zeiten herunter.
"""
from __future__ import annotations

import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Literal

from nexcore.settings import HIDDEN, SettingsStore
from nexproto.termine import TERMINE, termin, termin_ab
from pydantic import Field

from .config import _Strict

SETTINGS_FILE = "aion2.schedule.yaml"
WEEK_START = datetime(1970, 1, 5, tzinfo=timezone.utc).timestamp()  # ein Montag, 00:00 UTC
BUILTIN_NAMES = tuple(name for name, *_ in TERMINE)


class Event(_Strict):
    """Eigenes Ereignis. Start in Minuten ab Montag 00:00 (Zeitzone tz); bei Wiederholungen unter einer
    Woche also einfach ab Mitternacht bzw. zur vollen Stunde."""
    name: str = Field(min_length=1, max_length=40)
    every: int = Field(60, ge=1, le=10080)
    at: int = Field(0, ge=0, le=10079)
    open: int = Field(0, ge=0, le=1440)  # so lange ist es „offen“ (0 = Zeitpunkt)
    tz: Literal["local", "utc"] = "local"
    enabled: bool = True


class ScheduleSettings(_Strict):
    # beides bearbeitet die Seite „Termine“ selbst (Tabelle), kein Formular
    events: list[Event] = Field(default_factory=list, max_length=24, json_schema_extra=HIDDEN)
    hidden: list[str] = Field(default_factory=list, max_length=len(BUILTIN_NAMES), json_schema_extra=HIDDEN)


def event_reference(event: Event, now: float) -> float:
    """Bezugszeit eines eigenen Ereignisses in Sekunden seit 1970. Ortszeit mit dem Versatz von jetzt,
    damit „20:00“ auch nach der Zeitumstellung 20:00 bleibt."""
    offset = datetime.fromtimestamp(now).astimezone().utcoffset()
    shift = offset.total_seconds() if event.tz == "local" and offset else 0
    return WEEK_START + event.at * 60 - shift


def _row(name: str, start_open: tuple[float, bool], open_min: int, own: bool, shown: bool) -> dict[str, Any]:
    start, is_open = start_open
    return {"name": name, "start": start, "open_until": start + open_min * 60 if is_open else None,
            "own": own, "shown": shown}


class Schedule:
    def __init__(self, config_dir: Path) -> None:
        self.store = SettingsStore(config_dir / SETTINGS_FILE, ScheduleSettings,
                                   header="Termine: eigene Ereignisse und ausgeblendete feste Termine")

    def entries(self, now: float | None = None) -> list[dict[str, Any]]:
        """Alle Termine in fester Reihenfolge: erst die der Server, dann die eigenen (wie in den Einstellungen)."""
        now = time.time() if now is None else now
        settings = self.store.value
        rows = [_row(name, termin(now, reference, every, open_min), open_min, False, name not in settings.hidden)
                for name, reference, every, open_min in TERMINE]
        for event in settings.events:
            start_open = termin_ab(now, event_reference(event, now), event.every, event.open)
            rows.append(_row(event.name, start_open, event.open, True, event.enabled))
        return rows

    def visible(self, now: float | None = None) -> list[dict[str, Any]]:
        """Was das Widget zeigt: nur eingeschaltete, offene zuerst, dann nach Beginn."""
        rows = [row for row in self.entries(now) if row["shown"]]
        return sorted(rows, key=lambda row: (row["open_until"] is None, row["start"]))
