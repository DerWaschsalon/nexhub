"""Feste Termine (termine.py): Server-Uhr mit Zeitumstellung, Wochentermine, offene Fenster.
Die Erwartungen im November stammen von kisk.app/timers/eu (abgerufen am 24.11.2026)."""
from datetime import datetime, timezone

from nexproto.termine import EVENT_BY_KEY, EVENTS, cycle, next_start, starts_between, upcoming


def utc(text: str) -> float:
    return datetime.fromisoformat(text).replace(tzinfo=timezone.utc).timestamp()


def start(key: str, now: str) -> float:
    return next_start(utc(now), EVENT_BY_KEY[key])[0]


def test_winterzeiten_wie_bei_kisk():
    now = "2026-11-24 15:30"
    assert start("rift", now) == utc("2026-11-24 16:00")
    assert start("shugo", now) == utc("2026-11-24 16:00")
    assert start("kaira", now) == utc("2026-11-24 18:00")
    assert start("daily_reset", now) == utc("2026-11-25 07:00")
    assert start("weekly_reset", now) == utc("2026-11-25 07:00")
    assert start("artifact_siege", now) == utc("2026-11-26 20:00")
    assert start("nahma", now) == utc("2026-11-27 20:00")


def test_wochentermine_wechseln_zwischen_ihren_tagen():
    assert start("artifact_siege", "2026-11-26 21:30") == utc("2026-11-28 20:00")  # nach Donnerstag: Samstag
    assert start("nahma", "2026-11-28 12:00") == utc("2026-11-29 20:00")  # Sonntag
    assert start("weekly_reset", "2026-11-25 07:05") == utc("2026-12-02 07:00")


def test_uhrzeit_bleibt_ueber_die_zeitumstellung():
    # Riss um 17:00 Serverzeit: im Sommer 15:00 UTC, im Winter 16:00 UTC
    assert start("rift", "2026-10-24 14:00") == utc("2026-10-24 15:00")
    assert start("rift", "2026-10-26 14:00") == utc("2026-10-26 16:00")
    assert start("daily_reset", "2027-03-29 00:00") == utc("2027-03-29 06:00")  # nach dem 28.03. wieder Sommerzeit


def test_offenes_fenster():
    siege = EVENT_BY_KEY["artifact_siege"]
    assert next_start(utc("2026-11-26 20:30"), siege) == (utc("2026-11-26 20:00"), True)
    assert next_start(utc("2026-11-26 21:00"), siege) == (utc("2026-11-28 20:00"), False)
    row = next(r for r in upcoming(utc("2026-11-26 20:30")) if r[0] is siege)
    assert row[2] == utc("2026-11-26 21:00")


def test_eigene_ereignisse_rechnen_ohne_server_uhr():
    assert cycle(utc("2026-11-24 20:10"), utc("2026-11-01 20:00"), 1440, 30) == (utc("2026-11-24 20:00"), True)
    assert cycle(utc("2026-11-24 20:40"), utc("2026-11-01 20:00"), 1440, 30) == (utc("2026-11-25 20:00"), False)


def test_schluessel_sind_eindeutig():
    assert len(EVENT_BY_KEY) == len(EVENTS)


def test_wochenplan():
    week = (utc("2026-11-24 12:00"), utc("2026-12-01 12:00"))
    assert starts_between(EVENT_BY_KEY["artifact_siege"], *week) == [utc("2026-11-26 20:00"), utc("2026-11-28 20:00")]
    assert starts_between(EVENT_BY_KEY["nahma"], *week) == [utc("2026-11-27 20:00"), utc("2026-11-29 20:00")]
    # mitten im offenen Fenster zählt die laufende Belagerung nicht mehr mit
    assert starts_between(EVENT_BY_KEY["artifact_siege"], utc("2026-11-26 20:30"), week[1]) == [utc("2026-11-28 20:00")]
