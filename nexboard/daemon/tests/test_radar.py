"""Radar: Einstellungen prüfen und mischen, Befehle, Start und Ende mit dem Spiel, Stand fürs Overlay."""
import asyncio
import json

import pytest

from deckbar_daemon import radar as modul
from deckbar_daemon.aion2 import settings
from deckbar_daemon.radar import Radar


class FakeService:
    """Steht statt des echten RadarService (der würde tcpdump starten)."""

    def __init__(self, name: str) -> None:
        self.name = name
        self.calls: list[str] = []
        self.recording = False
        self.error = None  # Mitschnitt läuft

    def start(self) -> None:
        self.calls.append("start")

    def stop(self) -> None:
        self.calls.append("stop")

    def reload(self) -> None:
        self.calls.append("reload")

    def test_warning(self) -> None:
        self.calls.append("test_warning")

    def test_callout(self, key: str) -> None:
        self.calls.append(f"test_callout {key}")

    def start_recording(self) -> None:
        self.recording = True

    def stop_recording(self) -> None:
        self.recording = False

    def tick(self) -> None:
        pass

    def state(self) -> dict:
        return {"cubes": []}


@pytest.fixture
def konfig(tmp_path):
    """Die Einstellungsdatei des Tests (conftest lenkt sie nach tmp_path um)."""
    return settings.FILE


def radar(**kw) -> tuple[Radar, list]:
    sent: list = []

    async def publish(state: dict) -> None:
        sent.append(state)
    return Radar(publish, service=FakeService, **kw), sent


def spiel(running):
    """Spiel-Abfrage für die Tests: running() sagt, ob AION 2 gerade „läuft“."""
    async def poll() -> bool:
        return running()
    return poll


async def warten_bis(bedingung, s: float = 3.0) -> None:
    for _ in range(int(s / 0.05)):
        if bedingung():
            return
        await asyncio.sleep(0.05)
    raise AssertionError("Bedingung nicht erfüllt")


async def test_speichern_mischt_und_behaelt_fremde_schluessel(konfig):
    r, _ = radar()
    konfig.write_text(json.dumps({"x": 5, "karte_x": 9}))
    info = await r.save({"reichweite": 300, "ton": False})
    assert info["einstellungen"]["reichweite"] == 300
    assert json.loads(konfig.read_text()) == {"x": 5, "karte_x": 9, "reichweite": 300, "ton": False}


@pytest.mark.parametrize("patch", [{"quatsch": 1}, {"x": 10}, {"reichweite": "weit"}, {"ton": 1}, {"reichweite": True},
                                   {"name": "X"}, {"sprache": "en"}])  # Name und Sprache: nur allgemein
async def test_speichern_lehnt_falsches_ab(konfig, patch):
    r, _ = radar()
    konfig.write_text('{"reichweite": 50}')
    with pytest.raises(ValueError):
        await r.save(patch)
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
        await r.command("warnung_testen")
    with pytest.raises(ValueError):
        await r.command("rm -rf")


async def test_startet_mit_spiel_meldet_stand_und_endet_nach_dem_spiel():
    spiel_an = True
    r, gesendet = radar(game_running=spiel(lambda: spiel_an), poll_s=0.05, linger_s=0.2)
    aufgabe = asyncio.create_task(r.watch())
    await warten_bis(lambda: r.running and gesendet)
    assert gesendet[-1] == {"aktiv": True, "cubes": []}
    service = r.service
    await r.command("warnung_testen")
    await r.command("ansage_testen", "thamon-red")
    await r.command("aufnahme_start")
    assert r.recording
    await r.save({"ton": False})
    assert service.calls == ["start", "test_warning", "test_callout thamon-red", "reload"]
    assert {"schluessel": "thamon-red", "art": "Zauber", "vorgabe": "Rot — keine physischen Angriffe",
            "zeile": "Es glüht rot auf!"} in r.info()["ansagen"]["ansage_thamon"]
    spiel_an = False
    await warten_bis(lambda: not r.running)
    assert service.calls[-1] == "stop" and gesendet[-1] == {"aktiv": False}
    spiel_an = True
    await warten_bis(lambda: r.running)
    aufgabe.cancel()  # Modul aus
    with pytest.raises(asyncio.CancelledError):
        await aufgabe
    assert not r.running and gesendet[-1] == {"aktiv": False}


async def test_neuer_charaktername_startet_das_radar_neu(konfig):
    r, _ = radar(game_running=spiel(lambda: True), poll_s=0.05)
    aufgabe = asyncio.create_task(r.watch())
    await warten_bis(lambda: r.running)
    alt = r.service
    r.sync_profile("Gamunex", "de")
    assert r.service is not alt and alt.calls[-1] == "stop" and r.service.name == "Gamunex"
    neu = r.service
    r.sync_profile("Gamunex", "fr")  # Ansagen gibt es nur deutsch und englisch: englisch, kein Neustart
    assert r.service is neu and json.loads(konfig.read_text()) == {"name": "Gamunex", "sprache": "en"}
    aufgabe.cancel()
    with pytest.raises(asyncio.CancelledError):
        await aufgabe


async def test_voreinstellung_der_warnungen(konfig):
    r, _ = radar()
    assert r.info()["preset"] == "wichtig"  # Standardwerte des Radars
    await r.save(modul.WARNING_PRESETS["alles"])
    assert r.info()["preset"] == "alles"
    assert modul.WARNING_PRESETS.keys() == {"aus", "wichtig", "alles"}
    await r.save({"warn_an": False})
    assert r.info()["preset"] == "aus"


def test_feldbosse_und_karte_ohne_laufendes_radar():
    r, _ = radar()
    assert isinstance(r.field_bosses(), list)
    assert r.map() == {"name": ""} and r.map_file("bild") is None


def test_kampf_ohne_laufendes_radar():
    r, _ = radar()
    assert r.fight_state() == {"groggy": False, "warnungen": []}


def test_tode_ueberleben_das_radar_und_gehoeren_zum_run():
    r, _ = radar()
    r._start()
    assert r.service.deaths is r.deaths  # der Dienst schreibt in die Liste des Daemons
    r.deaths.extend([{"t_ms": 100, "name": "A", "skill": 1}, {"t_ms": 500, "name": "B", "skill": 2}])
    r._stop()
    assert r.deaths_between(0, 200) == [{"t_ms": 100, "name": "A", "skill": 1}]


async def test_radar_laeuft_solange_ein_teil_an_ist():
    """Die Module Radar, Boss-Warnungen und Feldbosse teilen sich einen Dienst."""
    r, _ = radar(game_running=spiel(lambda: True), poll_s=0.05)
    r.enable("warnings")
    r.enable("radar")
    await warten_bis(lambda: r.running)
    service = r.service
    assert service.parts == {"warnings", "radar"}
    await r.disable("warnings")
    assert r.running and service.parts == {"radar"} and service.calls[-1] == "reload"  # Schalter übernommen
    await r.disable("radar")
    assert not r.running and service.calls[-1] == "stop"
    r.enable("field_bosses")  # geht wieder an
    await warten_bis(lambda: r.running)
    await r.disable("field_bosses")


def test_ausgeschaltete_teile_schweigen(tmp_path, monkeypatch):
    from deckbar_daemon.aion2.service import RadarService
    from deckbar_daemon.core import speech
    played = []
    monkeypatch.setattr(speech, "play", lambda file: played.append(file.name))
    monkeypatch.setattr(speech, "CACHE", tmp_path)
    service = RadarService(spawn_log=None)
    service.parts = {"field_bosses"}
    service.reload()
    service._ping_due = True
    service.test_warning()
    service.tick()
    assert service.state()["warnungen"] == [] and played == []  # Warnungen und Cube-Ton aus
    service.parts = {"radar", "warnings"}
    service.reload()
    service._ping_due = True
    service.test_warning()
    service.tick()
    assert [w["titel"] for w in service.state()["warnungen"]] == ["Todesmal"] and "ping.wav" in played


async def test_quelle_capture_nimmt_den_mitschnitt_und_ein_wechsel_startet_neu(konfig):
    class Capture:
        running, data_listeners = False, []
    made = []

    class Service(FakeService):
        def __init__(self, name: str, source=None) -> None:
            super().__init__(name)
            made.append(source)
    sent: list = []

    async def publish(state: dict) -> None:
        sent.append(state)
    r = Radar(publish, game_running=spiel(lambda: True), service=Service, poll_s=0.05, capture=Capture())
    r.enable("radar")
    await warten_bis(lambda: r.running)
    assert made == [None]  # Standard: eigenes Mitlesen
    await r.save({"quelle": "capture"})
    assert len(made) == 2 and made[1].capture is r.capture
    with pytest.raises(ValueError):
        await r.save({"quelle": "funk"})
    await r.disable("radar")
