"""Client.txt lesen: neue Zeilen holen und die Zeilen erkennen, die Module brauchen.

Das Spiel hängt nur an; per Polling statt inotify, weil Schreibzugriffe aus Proton/Wine nicht
zuverlässig gemeldet werden. Wird die Datei kürzer (Spiel hat sie neu angelegt), geht es von vorn los.
Erkannt wird wie in Exile-UI (client log.ahk, Log_Parse): Zonenwechsel, Login-Bildschirm, Aufstiege und
die Antwort auf /whois. Die Muster hängen am Zeilenformat des Spiels, damit Chat-Nachrichten mit
demselben Text nichts auslösen.
"""
from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path

# Beim Öffnen so viel vom Ende lesen: Zone und Stufen auch von Charakteren, die länger nicht aufgestiegen sind
INITIAL_SCAN_BYTES = 32 * 1024 * 1024
ZONE = re.compile(r'\] Generating level (\d+) area "([^"]+)" with seed \d+')
LEVEL_UP = re.compile(r"\] : (\S+) \(([A-Za-z]+)\) is now level (\d+)\s*$")
# Antwort auf /whois; in Fabios Log noch nie vorgekommen, Doppelpunkt davor deshalb wahlweise
WHOIS = re.compile(r"\] (?:: )?(\S+) is a level (\d+) (.+?) in the ")
LOGIN_SERVER = re.compile(r"\] connected to \S*\.login\.", re.IGNORECASE)
LOG_OPENED = "***** LOG FILE OPENING *****"  # Spiel gestartet: noch in keiner Zone


@dataclass(frozen=True)
class ZoneEntered:
    area_id: str
    area_level: int
    live: bool = True  # False = beim Öffnen aus alten Zeilen gelesen (nichts auslösen, nur übernehmen)


@dataclass(frozen=True)
class LevelUp:
    """Aufstieg oder /whois-Antwort. Kommt auch für Mitspieler: wer gemeint ist, entscheidet das Modul."""
    character: str
    char_class: str
    level: int
    live: bool = True


@dataclass(frozen=True)
class LoginScreen:
    """Charakterauswahl oder Spielstart: man steht in keiner Zone mehr."""
    live: bool = True


LogEvent = ZoneEntered | LevelUp | LoginScreen


def parse_line(line: str, live: bool = True) -> LogEvent | None:
    zone = ZONE.search(line)
    if zone:
        return ZoneEntered(zone.group(2), int(zone.group(1)), live)
    up = LEVEL_UP.search(line)
    if up:
        return LevelUp(up.group(1), up.group(2), int(up.group(3)), live)
    whois = WHOIS.search(line)
    if whois:
        return LevelUp(whois.group(1), whois.group(3), int(whois.group(2)), live)
    if LOGIN_SERVER.search(line) or LOG_OPENED in line:
        return LoginScreen(live)
    return None


class ClientLog:
    """Liest eine Client.txt ab einer gemerkten Stelle."""

    def __init__(self, path: Path) -> None:
        self.path = path
        self._pos = 0
        self._rest = b""  # angefangene Zeile vom letzten Lesen

    def open(self) -> list[LogEvent]:
        """Ab jetzt nur Neues lesen; zurück kommt der letzte Stand (live=False). Blockiert bei großen
        Dateien kurz: aus asyncio heraus in einem Thread aufrufen."""
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
    """Letzter Ort (Zone oder Login) und je Charakter die letzte Stufe, in der Reihenfolge, in der sie
    geschahen."""
    latest: dict[str, tuple[int, LogEvent]] = {}
    for index, line in enumerate(lines):
        event = parse_line(line, live=False)
        if isinstance(event, LevelUp):
            latest[f"level:{event.character}"] = (index, event)
        elif event:
            latest["where"] = (index, event)
    return [event for _, event in sorted(latest.values(), key=lambda pair: pair[0])]
