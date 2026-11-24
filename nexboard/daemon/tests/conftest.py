"""Tests laufen abgeschottet: kein Socket eines echten, laufenden Overlays im Laufzeitordner und kein
echter KDE-Starter (Tastenkürzel des Overlays).

Tests mit @pytest.mark.a2tools brauchen das Submodul capture/a2tools; ohne es (z. B. auf einem Server
ohne `git submodule update --init`) werden sie übersprungen statt rot zu werden."""
import pytest

from deckbar_daemon.aion2 import gamedata, spawn_points
from deckbar_daemon.aion2 import settings as radar_settings
from deckbar_daemon.meter_files import SDK


def pytest_collection_modifyitems(items):
    if SDK.exists():
        return
    skip = pytest.mark.skip(reason="Submodul capture/a2tools fehlt: git submodule update --init")
    for item in items:
        if "a2tools" in item.keywords:
            item.add_marker(skip)


@pytest.fixture(autouse=True)
def _isolated_runtime_dir(tmp_path, monkeypatch):
    monkeypatch.setenv("XDG_RUNTIME_DIR", str(tmp_path / "run"))
    monkeypatch.setenv("XDG_DATA_HOME", str(tmp_path / "share"))


@pytest.fixture(autouse=True)
def _default_radar_settings(tmp_path, monkeypatch):
    """Standardwerte des Radars statt der echten ~/.config/aion2-radar.json: sonst hängen Ansagetexte an der
    Sprache, die gerade eingestellt ist, und Tests könnten die Datei überschreiben."""
    monkeypatch.setattr(radar_settings, "FILE", tmp_path / "aion2-radar.json")
    monkeypatch.setattr(radar_settings, "_settings", None)
    # gesehene Spawnpunkte und Feldboss-Timer der Tests nicht in den echten Datenordner
    monkeypatch.setattr(spawn_points, "FILE", tmp_path / "cubepunkte.json")
    monkeypatch.setattr(gamedata, "STORE", tmp_path / "aion2-radar")
