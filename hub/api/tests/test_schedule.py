"""Seite „Termine“: der Zeitplan aus nexproto.termine, ohne Login."""
from datetime import UTC, datetime

from nexhub_api.modules.schedule import routes as schedule


def test_zeitplan_ohne_login(client, monkeypatch):
    now = datetime(2026, 11, 24, 15, 30, tzinfo=UTC).timestamp()
    monkeypatch.setattr(schedule.time, "time", lambda: now)
    d = client.get("/api/public/termine").json()
    assert d["now"] == now and d["server_zone"] == "Europe/Berlin"
    events = {e["key"]: e for e in d["events"]}
    assert events["rift"]["start"] == now + 30 * 60 and events["rift"]["open_until"] is None
    assert events["rift"]["name_de"] == "Riss" and events["kaira"]["place"] == "Chaotic Lower Reshanta"
    # Wochenplan: Reset am Mittwoch, dann Belagerung und Nahma im Wechsel
    assert [p["key"] for p in d["week"]] == ["weekly_reset", "artifact_siege", "nahma", "artifact_siege", "nahma"]


def test_laufender_termin_ist_offen(client, monkeypatch):
    now = datetime(2026, 11, 26, 20, 30, tzinfo=UTC).timestamp()  # Donnerstag 21:30 Serverzeit
    monkeypatch.setattr(schedule.time, "time", lambda: now)
    siege = next(e for e in client.get("/api/public/termine").json()["events"] if e["key"] == "artifact_siege")
    assert siege["start"] == now - 30 * 60 and siege["open_until"] == now + 30 * 60
