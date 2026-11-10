"""Umzug der Einstellungsdateien auf Modulnamen: einmal, mit Sicherung, ohne etwas zu überschreiben."""
import json

import yaml

from deckbar_daemon import schedule
from deckbar_daemon.migrate import RENAMED, migrate


def test_umzug_mit_sicherung(tmp_path):
    (tmp_path / "dps.yaml").write_text("enabled: true\n")
    (tmp_path / "runs.yaml").write_text("enabled: false\n")
    (tmp_path / RENAMED["runs.yaml"]).write_text("enabled: true\n")  # neue Datei gibt es schon: bleibt
    assert migrate(tmp_path) == ["dps.yaml"]
    assert (tmp_path / RENAMED["dps.yaml"]).read_text() == "enabled: true\n"
    assert not (tmp_path / "dps.yaml").exists()
    assert (tmp_path / RENAMED["runs.yaml"]).read_text() == "enabled: true\n"
    (backup,) = (tmp_path / "backup").iterdir()
    assert (backup / "dps.yaml").read_text() == "enabled: true\n"
    assert migrate(tmp_path) == []  # zweiter Start: nichts mehr zu tun


def test_schluessel_zieht_ins_richtige_modul(tmp_path):
    (tmp_path / "dps.yaml").write_text("source: capture\nauto_page: aion\n")
    assert migrate(tmp_path) == ["dps.yaml", f"{RENAMED['dps.yaml']}:auto_page"]
    assert yaml.safe_load((tmp_path / "deck.yaml").read_text()) == {"auto_page": "aion"}
    assert yaml.safe_load((tmp_path / RENAMED["dps.yaml"]).read_text()) == {"source": "capture"}
    (backup,) = (tmp_path / "backup").iterdir()
    assert (backup / "dps.yaml").read_text() == "source: capture\nauto_page: aion\n"  # Original gesichert
    assert migrate(tmp_path) == []


def test_sprache_und_charaktername_werden_allgemein(tmp_path):
    (tmp_path / "config.yaml").write_text("token: geheim12345\nname: NexBoard\n")
    (tmp_path / "config.yaml").chmod(0o600)
    (tmp_path / RENAMED["dps.yaml"]).write_text("source: capture\nlang: de\n")
    radar = tmp_path / "aion2-radar.json"
    radar.write_text(json.dumps({"name": "Gamunex", "sprache": "en"}))
    assert migrate(tmp_path, radar) == [f"{RENAMED['dps.yaml']}:lang", "character_name"]
    config = yaml.safe_load((tmp_path / "config.yaml").read_text())
    assert config == {"token": "geheim12345", "name": "NexBoard", "language": "de", "character_name": "Gamunex"}
    assert (tmp_path / "config.yaml").stat().st_mode & 0o777 == 0o600  # Token bleibt privat
    assert yaml.safe_load((tmp_path / RENAMED["dps.yaml"]).read_text()) == {"source": "capture"}
    assert migrate(tmp_path, radar) == []


def test_eigene_event_timer_ziehen_zu_den_terminen(tmp_path):
    (tmp_path / "overlay").mkdir()
    layout = {"widgets": {"timers": {"enabled": True, "events": [
        {"name": "Spacetime Rift", "every": 180, "at": 120},  # alte Voreinstellung
        {"name": "Riss", "every": 180},  # neue Voreinstellung (feste Termine)
        {"name": "Gilde", "every": 1440, "at": 1200, "tz": "local"}]}}}
    (tmp_path / "overlay" / "layout.json").write_text(json.dumps(layout))
    assert migrate(tmp_path) == ["overlay/layout.json:events"]
    assert yaml.safe_load((tmp_path / schedule.SETTINGS_FILE).read_text()) == {
        "events": [{"name": "Gilde", "every": 1440, "at": 1200, "tz": "local"}]}
    assert json.loads((tmp_path / "overlay" / "layout.json").read_text()) == {"widgets": {"timers": {"enabled": True}}}
    assert migrate(tmp_path) == []
