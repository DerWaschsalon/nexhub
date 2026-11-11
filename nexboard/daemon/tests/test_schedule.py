"""Termine: feste und eigene in einer Liste, Ortszeit, ausblenden, Weitergabe ans Overlay."""
import asyncio
from datetime import datetime, timezone

import yaml

from deckbar_daemon.app import NexBoard
from deckbar_daemon.config import Settings
from deckbar_daemon.schedule import BUILTIN_NAMES, SETTINGS_FILE, Event, Schedule, event_reference


def utc(day: int, hour: int, minute: int = 0) -> float:
    return datetime(2026, 11, day, hour, minute, tzinfo=timezone.utc).timestamp()


def test_feste_und_eigene_termine_in_einer_liste(tmp_path):
    (tmp_path / SETTINGS_FILE).write_text(yaml.safe_dump(
        {"events": [{"name": "Gilde", "every": 1440, "at": 20 * 60, "tz": "utc", "open": 30}],
         "hidden": ["Shugo-Fest"]}))
    rows = Schedule(tmp_path).entries(utc(10, 20, 10))
    assert [r["name"] for r in rows] == [*BUILTIN_NAMES, "Gilde"]
    gilde = rows[-1]
    assert gilde["own"] and gilde["start"] == utc(10, 20) and gilde["open_until"] == utc(10, 20, 30)
    assert not next(r for r in rows if r["name"] == "Shugo-Fest")["shown"]


def test_widget_zeigt_offene_zuerst_und_nur_sichtbare(tmp_path):
    (tmp_path / SETTINGS_FILE).write_text(yaml.safe_dump({"events": [
        {"name": "Aus", "every": 60, "enabled": False}], "hidden": list(BUILTIN_NAMES[1:])}))
    visible = Schedule(tmp_path).visible(utc(10, 3, 5))  # Riss: 03:00 UTC, 10 min offen
    assert [r["name"] for r in visible] == ["Riss"] and visible[0]["open_until"] == utc(10, 3, 10)


def test_ortszeit_folgt_der_uhr(monkeypatch):
    monkeypatch.setenv("TZ", "Europe/Berlin")
    import time
    time.tzset()
    try:
        event = Event(name="Abend", every=1440, at=20 * 60, tz="local")
        assert event_reference(event, utc(10, 12)) % 86400 == 19 * 3600  # Winter: 20:00 = 19:00 UTC
        assert event_reference(event, utc(7, 12) - 120 * 86400) % 86400 == 18 * 3600  # Sommer
    finally:
        monkeypatch.delenv("TZ")
        time.tzset()


async def test_overlay_bekommt_die_liste(tmp_path):
    deck = NexBoard(Settings(token="testtoken123", mdns=False, usb="off"), tmp_path, mdns=False)
    await deck.modules.set("aion2.schedule", True)
    await deck.modules.start()
    await asyncio.sleep(0.05)  # erste Runde der Aufgabe
    assert [r["name"] for r in deck.overlay.retained["schedule"]] and all(r["shown"] for r in deck.overlay.retained["schedule"])
    module = deck.modules.modules["aion2.schedule"]
    await module.update_settings({"hidden": list(BUILTIN_NAMES)})
    assert deck.overlay.retained["schedule"] == []  # sofort, nicht erst nach dem nächsten Takt
    await deck.modules.shutdown()
