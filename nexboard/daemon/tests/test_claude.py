"""claude.py: Antwort des Nutzungs-Endpunkts → Werte für die Claude-Kachel."""
from datetime import datetime

from deckbar_daemon.claude import summary


def test_summary_rundet_und_nennt_wochentag():
    now = datetime(2026, 10, 29, 9, 0).astimezone()
    # Endpunkt liefert UTC knapp vor der vollen Stunde
    session = datetime(2026, 10, 29, 10, 59, 59, 600000).astimezone()
    week = datetime(2026, 10, 31, 0, 59, 59, 600000).astimezone()
    data = {"five_hour": {"utilization": 31.4, "resets_at": session.isoformat()},
            "seven_day": {"utilization": 48.0, "resets_at": week.isoformat()}}
    assert summary(data, now) == {"session": {"pct": 31, "reset": "11:00"},
                                  "week": {"pct": 48, "reset": "Sa 01:00"}}


def test_summary_ohne_werte():
    now = datetime(2026, 10, 29, 9, 0).astimezone()
    assert summary({"five_hour": None, "seven_day": {"utilization": None}}, now) == {}
