"""Feste Termine der globalen AION-2-Server (EU/NA): Riss, Shugo-Fest, Beritra-Luftangriff, Wächterin
Kaira, Resets. Gebraucht vom Radar (NexBoard-Seite, Ansagen) und vom Bot (Termin-Tafel).

Nur Standardbibliothek: Der Bot kopiert genau diese Datei in sein Image (bot/Dockerfile), ohne den
Rest von nexproto. Quelle jackships/aion2-data; dort ist nur der Riss „confirmed“, der Rest „likely“.
"""
from __future__ import annotations

from datetime import datetime, timezone

# (Name, Bezugszeit UTC, alle Minuten, offen Minuten). In UTC, damit die Zeitumstellung nichts verschiebt.
TERMINE = [
    ("Riss", "2026-10-07 00:00", 180, 10),
    ("Shugo-Fest", "2026-10-07 00:00", 60, 10),
    ("Beritra-Luftangriff", "2026-10-07 00:30", 60, 10),
    ("Wächterin Kaira", "2026-10-07 01:00", 180, 30),
    ("Tages-Reset", "2026-10-07 07:00", 1440, 1),
    ("Wochen-Reset", "2026-10-07 07:00", 10080, 1),  # Mittwoch
]


def termin(jetzt: float, bezug: str, alle: int, offen: int) -> tuple[float, bool]:
    """(Beginn des naechsten oder laufenden Termins in Sekunden seit 1970, gerade offen?)."""
    return termin_ab(jetzt, datetime.fromisoformat(bezug).replace(tzinfo=timezone.utc).timestamp(), alle, offen)


def termin_ab(jetzt: float, start: float, alle: int, offen: int) -> tuple[float, bool]:
    """Wie termin(), mit dem Bezug als Sekunden seit 1970 (eigene Ereignisse der NexBoard)."""
    beginn = start + -(-(jetzt - start) // (alle * 60)) * alle * 60  # naechster Beginn ab jetzt
    if jetzt < beginn - alle * 60 + offen * 60:
        return beginn - alle * 60, True
    return beginn, False


def alle(jetzt: float) -> list[tuple[str, float, float | None]]:
    """Jeder Termin als (Name, Beginn, offen bis oder None), in der Reihenfolge von TERMINE."""
    zeilen = []
    for name, bezug, abstand, dauer in TERMINE:
        beginn, offen = termin(jetzt, bezug, abstand, dauer)
        zeilen.append((name, beginn, beginn + dauer * 60 if offen else None))
    return zeilen
