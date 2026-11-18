"""Client.txt lesen: neue Zeilen holen und die Zeilen erkennen, die Module brauchen.

Das Spiel hängt nur an; per Polling statt inotify, weil Schreibzugriffe aus Proton/Wine nicht
zuverlässig gemeldet werden. Wird die Datei kürzer (Spiel hat sie neu angelegt), geht es von vorn los.
"""
from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path

# Beim Öffnen so viel vom Ende lesen, um Zone und Stufe vor dem Start des Daemons zu kennen
INITIAL_SCAN_BYTES = 8 * 1024 * 1024
ZONE = re.compile(r'Generating level (\d+) area "([^"]+)" with seed (\d+)')
LEVEL_UP = re.compile(r": (\S+) \(([A-Za-z]+)\) is now level (\d+)\s*$")


@dataclass(frozen=True)
class ZoneEntered:
    area_id: str
    area_level: int
    live: bool = True  # False = beim Öffnen aus alten Zeilen gelesen (nichts auslösen, nur übernehmen)


@dataclass(frozen=True)
class LevelUp:
    character: str
    char_class: str
    level: int
    live: bool = True


LogEvent = ZoneEntered | LevelUp


def parse_line(line: str, live: bool = True) -> LogEvent | None:
    zone = ZONE.search(line)
    if zone:
        return ZoneEntered(zone.group(2), int(zone.group(1)), live)
    level = LEVEL_UP.search(line)
    if level:
        return LevelUp(level.group(1), level.group(2), int(level.group(3)), live)
    return None


class ClientLog:
    """Liest eine Client.txt ab einer gemerkten Stelle."""

    def __init__(self, path: Path) -> None:
        self.path = path
        self._pos = 0
        self._rest = b""  # angefangene Zeile vom letzten Lesen

    def open(self) -> list[LogEvent]:
        """Ab jetzt nur Neues lesen; zurück kommen letzte Zone und letzte Aufstiege (live=False)."""
        try:
            with self.path.open("rb") as f:
                size = f.seek(0, 2)
                f.seek(max(size - INITIAL_SCAN_BYTES, 0))
                data = f.read()
        except OSError:
            return []
        self._pos, self._rest = size, b""
        return last_state(data.decode(errors="replace").splitlines())

    def read_new(self) -> list[LogEvent]:
        """Neue vollständige Zeilen seit dem letzten Aufruf, als Ereignisse."""
        try:
            with self.path.open("rb") as f:
                size = f.seek(0, 2)
                if size < self._pos:  # neu angelegt
                    self._pos, self._rest = 0, b""
                f.seek(self._pos)
                data = self._rest + f.read(size - self._pos)
        except OSError:
            return []
        self._pos = size
        complete, _, self._rest = data.rpartition(b"\n")
        events = [parse_line(line) for line in complete.decode(errors="replace").splitlines()]
        return [e for e in events if e]


def last_state(lines: list[str]) -> list[LogEvent]:
    """Letzte Zone und je Charakter den letzten Aufstieg, in der Reihenfolge, in der sie geschahen."""
    latest: dict[str, tuple[int, LogEvent]] = {}
    for index, line in enumerate(lines):
        event = parse_line(line, live=False)
        if isinstance(event, ZoneEntered):
            latest["zone"] = (index, event)
        elif isinstance(event, LevelUp):
            latest[f"level:{event.character}"] = (index, event)
    return [event for _, event in sorted(latest.values(), key=lambda pair: pair[0])]
