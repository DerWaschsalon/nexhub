"""Tests laufen abgeschottet: kein Socket eines echten, laufenden Overlays im Laufzeitordner und kein
echter KDE-Starter (Tastenkürzel des Overlays)."""
import pytest


@pytest.fixture(autouse=True)
def _isolated_runtime_dir(tmp_path, monkeypatch):
    monkeypatch.setenv("XDG_RUNTIME_DIR", str(tmp_path / "run"))
    monkeypatch.setenv("XDG_DATA_HOME", str(tmp_path / "share"))
