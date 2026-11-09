"""Umzug der Einstellungsdateien auf Modulnamen: einmal, mit Sicherung, ohne etwas zu überschreiben."""
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
