"""Jeder Test mit den Standardwerten des Radars statt der echten ~/.config/aion2-radar.json: sonst hängen
Ansagetexte an der Sprache, die gerade eingestellt ist, und Tests könnten die Datei überschreiben."""
import pytest

from radar import konfig


@pytest.fixture(autouse=True)
def eigene_einstellungen(tmp_path, monkeypatch):
    monkeypatch.setattr(konfig, "KONFIG", tmp_path / "aion2-radar.json")
    monkeypatch.setattr(konfig, "_konfig", None)
