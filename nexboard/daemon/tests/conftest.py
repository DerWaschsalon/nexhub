"""Tests laufen abgeschottet: kein Socket eines echten, laufenden Overlays im Laufzeitordner."""
import pytest


@pytest.fixture(autouse=True)
def _isolated_runtime_dir(tmp_path, monkeypatch):
    monkeypatch.setenv("XDG_RUNTIME_DIR", str(tmp_path / "run"))
