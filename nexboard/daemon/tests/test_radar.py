"""Radar: Einstellungen prüfen und mischen, Befehle, Start und Ende mit dem Spiel, Stand fürs Overlay."""
import asyncio

import pytest
from pydantic import ValidationError

from deckbar_daemon import radar as modul
from deckbar_daemon.radar import Radar


class FakeService:
    """Steht statt des echten RadarService (der würde tcpdump starten)."""

    def __init__(self, name: str, settings=None, language: str = "de") -> None:
        self.name, self.settings, self.language = name, settings, language
        self.calls: list[str] = []
        self.recording = False
        self.error = None  # Mitschnitt läuft

    def start(self) -> None:
        self.calls.append("start")

    def stop(self) -> None:
        self.calls.append("stop")

    def reload(self, language: str | None = None) -> None:
        self.language = language or self.language
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
    """Ordner der Einstellungen des Tests."""
    return tmp_path / "config"


def radar(folder, **kw) -> tuple[Radar, list]:
    sent: list = []

    async def publish(state: dict) -> None:
        sent.append(state)
    folder.mkdir(exist_ok=True)
    return Radar(publish, folder, service=FakeService, **kw), sent


def save(r: Radar, part: str, patch: dict) -> None:
    """Wie die Route /api/m/<Modul>/settings: prüfen, dann speichern."""
    r.save(part, r.stores[part].merge(patch))


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


def test_speichern_je_modul_in_eigener_datei(konfig):
    r, _ = radar(konfig)
    save(r, "radar", {"range_m": 300, "sound": False})
    save(r, "field_bosses", {"announce": False})
    assert r.settings.radar.range_m == 300 and not r.settings.radar.sound and not r.settings.field_bosses.announce
    assert "range_m: 300" in (konfig / "aion2.radar.yaml").read_text()
    neu, _ = radar(konfig)  # nach einem Neustart wieder da
    assert neu.settings.radar.range_m == 300 and not neu.settings.field_bosses.announce


@pytest.mark.parametrize("patch", [{"quatsch": 1}, {"range_m": "weit"}, {"source": "wlan"}, {"reichweite": 50}])
def test_speichern_lehnt_falsches_ab(konfig, patch):
    r, _ = radar(konfig)
    with pytest.raises(ValidationError):
        save(r, "radar", patch)
    assert r.settings.radar.range_m == 150 and not (konfig / "aion2.radar.yaml").exists()


def test_kaputte_oder_fehlende_datei_gibt_standard(konfig):
    konfig.mkdir()
    (konfig / "aion2.radar.yaml").write_text("{{")
    r, _ = radar(konfig)
    assert r.settings.radar.range_m == 150 and not r.info()["laeuft"]
    assert "Feuertempel" in r.info()["meldungen"]["dungeons"]
    assert r.settings.warnings.sounds["casts"] == "aus"  # Standard-Töne, auch ohne eigene


def test_eigene_toene_behalten_die_standard_toene(konfig):
    r, _ = radar(konfig)
    save(r, "warnings", {"sounds": {"flamme": "piep"}})
    assert r.settings.warnings.sounds == {"schwert": "aus", "casts": "aus", "zikel_angriffe": "aus", "flamme": "piep"}


async def test_befehle_ohne_radar_und_unbekannt(konfig):
    r, _ = radar(konfig)
    with pytest.raises(RuntimeError):
        await r.command("warnung_testen")
    with pytest.raises(ValueError):
        await r.command("rm -rf")


async def test_startet_mit_spiel_meldet_stand_und_endet_nach_dem_spiel(konfig):
    spiel_an = True
    r, gesendet = radar(konfig, game_running=spiel(lambda: spiel_an), poll_s=0.05, linger_s=0.2)
    aufgabe = asyncio.create_task(r.watch())
    await warten_bis(lambda: r.running and gesendet)
    assert gesendet[-1] == {"aktiv": True, "cubes": []}
    service = r.service
    await r.command("warnung_testen")
    await r.command("ansage_testen", "thamon-red")
    await r.command("aufnahme_start")
    assert r.recording
    save(r, "radar", {"sound": False})
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
    r, _ = radar(konfig, game_running=spiel(lambda: True), poll_s=0.05)
    aufgabe = asyncio.create_task(r.watch())
    await warten_bis(lambda: r.running)
    alt = r.service
    r.sync_profile("Gamunex", "de")
    assert r.service is not alt and alt.calls[-1] == "stop" and r.service.name == "Gamunex"
    neu = r.service
    r.sync_profile("Gamunex", "fr")  # Ansagen gibt es nur deutsch und englisch: englisch, kein Neustart
    assert r.service is neu and neu.language == "en" and neu.calls[-1] == "reload"
    aufgabe.cancel()
    with pytest.raises(asyncio.CancelledError):
        await aufgabe


async def test_voreinstellung_der_warnungen(konfig):
    r, _ = radar(konfig)
    assert r.info()["preset"] == "wichtig"  # Standardwerte des Radars
    save(r, "warnings", modul.WARNING_PRESETS["alles"])
    assert r.info()["preset"] == "alles"
    assert modul.WARNING_PRESETS.keys() == {"aus", "wichtig", "alles"}
    save(r, "warnings", {"enabled": False})
    assert r.info()["preset"] == "aus"
    save(r, "warnings", {"enabled": True, "only_me": True, "off": ["flamme"]})
    assert r.info()["preset"] == "wichtig"  # Einzelheiten unter „Erweitert“ ändern die Voreinstellung nicht


def test_feldbosse_und_karte_ohne_laufendes_radar(konfig):
    r, _ = radar(konfig)
    assert isinstance(r.field_bosses(), list)
    assert r.map() == {"name": ""} and r.map_file("bild") is None


def test_kampf_ohne_laufendes_radar(konfig):
    r, _ = radar(konfig)
    assert r.fight_state() == {"groggy": False, "warnungen": []}


def test_tode_ueberleben_das_radar_und_gehoeren_zum_run(konfig):
    r, _ = radar(konfig)
    r._start()
    assert r.service.deaths is r.deaths  # der Dienst schreibt in die Liste des Daemons
    r.deaths.extend([{"t_ms": 100, "name": "A", "skill": 1}, {"t_ms": 500, "name": "B", "skill": 2}])
    r._stop()
    assert r.deaths_between(0, 200) == [{"t_ms": 100, "name": "A", "skill": 1}]


async def test_radar_laeuft_solange_ein_teil_an_ist(konfig):
    """Die Module Radar, Boss-Warnungen und Feldbosse teilen sich einen Dienst."""
    r, _ = radar(konfig, game_running=spiel(lambda: True), poll_s=0.05)
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
        def __init__(self, name: str, source=None, **kw) -> None:
            super().__init__(name, **kw)
            made.append(source)
    r, _ = radar(konfig, game_running=spiel(lambda: True), poll_s=0.05, capture=Capture())
    r.new_service = Service
    r.enable("radar")
    await warten_bis(lambda: r.running)
    assert made == [None]  # Standard: eigenes Mitlesen
    save(r, "radar", {"source": "capture"})
    assert len(made) == 2 and made[1].capture is r.capture
    await r.disable("radar")
