import pytest
from pydantic import BaseModel, Field, ValidationError

from nexcore.settings import MASK, SettingsStore


class Beispiel(BaseModel):
    name: str = "NexBoard"
    takt: int = Field(500, ge=100)
    webhook: str = Field("", json_schema_extra={"secret": True})


def test_fehlt_und_ungueltige_felder(tmp_path):
    path = tmp_path / "x.yaml"
    assert SettingsStore(path, Beispiel).value == Beispiel()
    path.write_text("name: Leiste\ntakt: 5\n")  # takt zu klein: nur dieses Feld fällt zurück
    assert SettingsStore(path, Beispiel).value == Beispiel(name="Leiste")


def test_migration(tmp_path):
    path = tmp_path / "x.yaml"
    path.write_text("titel: Alt\n")
    store = SettingsStore(path, Beispiel, migrate=lambda d: {"name": d.pop("titel")} | d)
    assert store.value.name == "Alt"


def test_geheimnisse(tmp_path):
    path = tmp_path / "x.yaml"
    store = SettingsStore(path, Beispiel, header="Beispiel – enthält Geheimnisse")
    store.update({"webhook": "https://example.com/geheim"})
    assert path.read_text().startswith("# Beispiel – enthält Geheimnisse\n")
    assert store.public()["webhook"] == MASK
    assert path.stat().st_mode & 0o777 == 0o600
    store.update({"webhook": MASK, "name": "Neu"})  # Punkte zurück: Geheimnis bleibt
    assert SettingsStore(path, Beispiel).value == Beispiel(name="Neu", webhook="https://example.com/geheim")
    with pytest.raises(ValidationError):
        store.update({"takt": 1})
    assert store.value.takt == 500
