"""Feste Termine der globalen AION-2-Server (EU): Riss, Shugo-Fest, Beritra-Luftangriff, Wächterin Kaira,
Resets, Artefakt-Belagerung, Wächterfürst Nahma. Gebraucht von NexBoard (Seite und Widget „Termine“,
Ansagen des Radars), vom Bot (Termin-Tafel) und vom Hub.

Die Zeiten stehen auf der Uhr des EU-Servers (SERVER_ZONE): Der Riss beginnt im Sommer wie im Winter um
17:00 Serverzeit, in UTC verschiebt er sich mit der Zeitumstellung. Abgeglichen am 24.11.2026 mit
kisk.app/timers/eu; der Beritra-Luftangriff steht dort nicht und bleibt wie bei jackships/aion2-data.

Nur Standardbibliothek, damit jeder Teil des Monorepos die Datei ohne weitere Pakete nutzen kann.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfo

SERVER_ZONE = ZoneInfo("Europe/Berlin")
HOUR_MIN = 60
DAY_MIN = 24 * HOUR_MIN
WEEK_MIN = 7 * DAY_MIN
MONDAY = datetime(2026, 10, 5)  # ein Montag, Bezug für alle Wochentage
WEDNESDAY, THURSDAY, FRIDAY, SATURDAY, SUNDAY = 2, 3, 4, 5, 6  # Tage ab Montag


@dataclass(frozen=True)
class Event:
    """Ein fester Termin. `at` ist eine Uhrzeit auf der Server-Uhr, ab der er sich alle `every_min` Minuten
    wiederholt; mit `weekdays` gilt `at` nur an diesen Tagen (dann ist `every_min` eine Woche)."""
    key: str
    name_de: str
    name_en: str
    at: str
    every_min: int
    open_min: int
    weekdays: tuple[int, ...] = ()
    place: str = ""  # Karte, wie das Spiel sie auf Englisch nennt


EVENTS = (
    Event("rift", "Riss", "Spacetime Rift", "02:00", 3 * HOUR_MIN, 10, place="Verteron, Eltnen, Altgard, Morheim"),
    Event("shugo", "Shugo-Fest", "Shugo Festival", "00:00", HOUR_MIN, 8),
    Event("beritra", "Beritra-Luftangriff", "Beritra Air Raid", "00:30", HOUR_MIN, 10),
    Event("kaira", "Wächterin Kaira", "Watcher Kaira", "01:00", 3 * HOUR_MIN, 30, place="Chaotic Lower Reshanta"),
    Event("daily_reset", "Tages-Reset", "Daily Reset", "08:00", DAY_MIN, 1),
    Event("weekly_reset", "Wochen-Reset", "Weekly Reset", "08:00", WEEK_MIN, 1, weekdays=(WEDNESDAY,)),
    Event("artifact_siege", "Artefakt-Belagerung", "Artifact Siege", "21:00", WEEK_MIN, 60,
          weekdays=(THURSDAY, SATURDAY), place="Chaotic Lower Reshanta"),
    Event("nahma", "Wächterfürst Nahma", "Guardian Lord Nahma", "21:00", WEEK_MIN, 30,
          weekdays=(FRIDAY, SUNDAY), place="Chaotic Lower and Middle Reshanta"),
)
EVENT_BY_KEY = {event.key: event for event in EVENTS}


def cycle(now: float, start: float, every_min: int, open_min: int) -> tuple[float, bool]:
    """Ein Termin, der ab `start` alle `every_min` Minuten beginnt: (Beginn des laufenden oder nächsten in
    Sekunden seit 1970, gerade offen?). Auch für die eigenen Ereignisse der NexBoard."""
    period = every_min * 60
    following = start + -(-(now - start) // period) * period  # nächster Beginn ab jetzt
    if now < following - period + open_min * 60:
        return following - period, True
    return following, False


def _server_clock(now: float) -> float:
    """Die Uhr des Servers als Sekunden, als wäre sie UTC. Darauf rechnet cycle() ohne Zeitumstellung."""
    return datetime.fromtimestamp(now, SERVER_ZONE).replace(tzinfo=timezone.utc).timestamp()


def _real_time(server_clock: float) -> float:
    return datetime.fromtimestamp(server_clock, timezone.utc).replace(tzinfo=SERVER_ZONE).timestamp()


def _anchors(event: Event) -> list[float]:
    """Je Wochentag des Termins ein erster Beginn auf der Server-Uhr (ohne Wochentage: einer)."""
    hour, minute = event.at.split(":")
    first = MONDAY + timedelta(hours=int(hour), minutes=int(minute))
    days = event.weekdays or (0,)
    return [(first + timedelta(days=day)).replace(tzinfo=timezone.utc).timestamp() for day in days]


def next_start(now: float, event: Event) -> tuple[float, bool]:
    """(Beginn des laufenden oder nächsten Termins in Sekunden seit 1970, gerade offen?)."""
    clock = _server_clock(now)
    found = [cycle(clock, anchor, event.every_min, event.open_min) for anchor in _anchors(event)]
    start, is_open = min(found, key=lambda one: (not one[1], one[0]))  # ein offener zuerst, sonst der früheste
    return _real_time(start), is_open


def upcoming(now: float) -> list[tuple[Event, float, float | None]]:
    """Jeder Termin als (Termin, Beginn, offen bis oder None), in der Reihenfolge von EVENTS."""
    rows = []
    for event in EVENTS:
        start, is_open = next_start(now, event)
        rows.append((event, start, start + event.open_min * 60 if is_open else None))
    return rows
