"""Radar: Einstellungen prüfen und mischen, Befehle, Start und Ende mit dem Spiel, Stand fürs Overlay."""
import asyncio
import json

import pytest

from deckbar_daemon import radar as modul
from deckbar_daemon.radar import Radar


class FakeDienst:
    """Steht statt des echten RadarDienst (der würde tcpdump starten)."""

    def __init__(self, name: str) -> None:
        self.name = name
        self.aufrufe: list[str] = []
        self.aufnahme = False
        self.quelle = self

    def starten(self) -> None:
        self.aufrufe.append("starten")

    def stoppen(self) -> None:
        self.aufrufe.append("stoppen")

    def neu_laden(self) -> None:
        self.aufrufe.append("neu_laden")

    def warnung_testen(self) -> None:
        self.aufrufe.append("warnung_testen")

    def pvp_neu(self) -> None:
        self.aufrufe.append("pvp_neu")

    def aufnahme_starten(self) -> None:
        self.aufnahme = True

    def aufnahme_stoppen(self) -> None:
        self.aufnahme = False

    def takt(self) -> None:
        pass

    def stand(self) -> dict:
        return {"cubes": []}


@pytest.fixture(autouse=True)
def konfig(tmp_path, monkeypatch):
    """Einstellungen in tmp_path statt ~/.config."""
    datei = tmp_path / "aion2-radar.json"
    monkeypatch.setattr(modul.konfig, "KONFIG", datei)
    monkeypatch.setattr(modul.konfig, "_konfig", None)
    return datei


def radar(**kw) -> tuple[Radar, list]:
    gesendet: list = []

    async def veroeffentlichen(stand: dict) -> None:
        gesendet.append(stand)
    return Radar(veroeffentlichen, dienst=FakeDienst, **kw), gesendet


def spiel(laeuft):
    """Spiel-Abfrage für die Tests: laeuft() sagt, ob AION 2 gerade „läuft“."""
    async def abfrage() -> bool:
        return laeuft()
    return abfrage


async def warten_bis(bedingung, s: float = 3.0) -> None:
    for _ in range(int(s / 0.05)):
        if bedingung():
            return
        await asyncio.sleep(0.05)
    raise AssertionError("Bedingung nicht erfüllt")


async def test_speichern_mischt_und_behaelt_fremde_schluessel(konfig):
    r, _ = radar()
    konfig.write_text(json.dumps({"x": 5, "karte_x": 9}))
    info = await r.speichern({"reichweite": 300, "ton": False})
    assert info["einstellungen"]["reichweite"] == 300
    assert json.loads(konfig.read_text()) == {"x": 5, "karte_x": 9, "reichweite": 300, "ton": False}


@pytest.mark.parametrize("patch", [{"quatsch": 1}, {"x": 10}, {"reichweite": "weit"}, {"ton": 1}, {"reichweite": True}])
async def test_speichern_lehnt_falsches_ab(konfig, patch):
    r, _ = radar()
    konfig.write_text('{"reichweite": 50}')
    with pytest.raises(ValueError):
        await r.speichern(patch)
    assert konfig.read_text() == '{"reichweite": 50}'


def test_kaputte_oder_fehlende_datei_gibt_standard(konfig):
    r, _ = radar()
    assert r.info()["einstellungen"]["reichweite"] == 150
    konfig.write_text("{{")
    info = r.info()
    assert info["einstellungen"]["name"] == "" and not info["laeuft"]
    assert "Feuertempel" in info["meldungen"]["dungeons"]


async def test_befehle_ohne_radar_und_unbekannt():
    r, _ = radar()
    with pytest.raises(RuntimeError):
        await r.befehl("warnung_testen")
    with pytest.raises(ValueError):
        await r.befehl("rm -rf")


async def test_startet_mit_spiel_meldet_stand_und_endet_nach_dem_spiel():
    spiel_an = True
    r, gesendet = radar(spiel_laeuft=spiel(lambda: spiel_an), abfrage_s=0.05, nachlauf_s=0.2)
    aufgabe = asyncio.create_task(r.watch())
    await warten_bis(lambda: r.laeuft and gesendet)
    assert gesendet[-1] == {"aktiv": True, "cubes": []}
    dienst = r.dienst
    await r.befehl("warnung_testen")
    await r.befehl("pvp_neu")
    await r.befehl("aufnahme_start")
    assert r.aufnahme
    await r.speichern({"ton": False})
    assert dienst.aufrufe == ["starten", "warnung_testen", "pvp_neu", "neu_laden"]
    spiel_an = False
    await warten_bis(lambda: not r.laeuft)
    assert dienst.aufrufe[-1] == "stoppen" and gesendet[-1] == {"aktiv": False}
    spiel_an = True
    await warten_bis(lambda: r.laeuft)
    aufgabe.cancel()  # Modul aus
    with pytest.raises(asyncio.CancelledError):
        await aufgabe
    assert not r.laeuft and gesendet[-1] == {"aktiv": False}


async def test_neustart_liest_den_namen_neu(konfig):
    r, _ = radar(spiel_laeuft=spiel(lambda: True), abfrage_s=0.05)
    aufgabe = asyncio.create_task(r.watch())
    await warten_bis(lambda: r.laeuft)
    alt = r.dienst
    konfig.write_text(json.dumps({"name": "Gamunex"}))
    await r.befehl("neustart")
    assert r.dienst is not alt and alt.aufrufe[-1] == "stoppen" and r.dienst.name == "Gamunex"
    aufgabe.cancel()
    with pytest.raises(asyncio.CancelledError):
        await aufgabe


def test_uebersicht_ohne_laufendes_radar():
    r, _ = radar()
    u = r.uebersicht()
    assert [t["name"] for t in u["termine"]][:2] == ["Riss", "Shugo-Fest"]
    assert u["vertraute"] and all("fehlen" in v for v in u["vertraute"])
    assert r.karte() == {"name": ""} and r.kartendatei("bild") is None
