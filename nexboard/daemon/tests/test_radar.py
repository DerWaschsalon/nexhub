"""Radar: Einstellungen prüfen und mischen, Befehle, Start und Ende mit dem Spiel."""
import asyncio
import json
import sys

import pytest

from deckbar_daemon.radar import Radar

# steht statt des echten Radars: meldet eine Aufnahme, schreibt Befehle in eine Datei, wartet auf stdin
FAKE = ("import sys; print('aufnahme an', flush=True)\n"
        "for z in sys.stdin: open('befehle.txt', 'a').write(z)")


def radar(tmp_path, **kw) -> Radar:
    return Radar(konfig=tmp_path / "aion2-radar.json", arbeitsordner=tmp_path,
                 programm=[sys.executable, "-c", FAKE], **kw)


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


async def test_speichern_mischt_und_behaelt_fremde_schluessel(tmp_path):
    r = radar(tmp_path)
    r.konfig.write_text(json.dumps({"x": 5, "karte_x": 9}))
    info = await r.speichern({"groesse": 300, "deckkraft": 1})
    assert info["einstellungen"]["groesse"] == 300
    assert json.loads(r.konfig.read_text()) == {"x": 5, "karte_x": 9, "groesse": 300, "deckkraft": 1}


@pytest.mark.parametrize("patch", [{"quatsch": 1}, {"x": 10}, {"groesse": "gross"}, {"ton": 1}, {"groesse": True}])
async def test_speichern_lehnt_falsches_ab(tmp_path, patch):
    r = radar(tmp_path)
    r.konfig.write_text('{"groesse": 200}')
    with pytest.raises(ValueError):
        await r.speichern(patch)
    assert r.konfig.read_text() == '{"groesse": 200}'


def test_kaputte_oder_fehlende_datei_gibt_standard(tmp_path):
    r = radar(tmp_path)
    assert r.info()["einstellungen"]["groesse"] == 260
    r.konfig.write_text("{{")
    info = r.info()
    assert info["einstellungen"]["name"] == "" and not info["laeuft"]
    assert "Feuertempel" in info["meldungen"]["dungeons"]


async def test_befehle_ohne_radar_und_unbekannt(tmp_path):
    r = radar(tmp_path)
    with pytest.raises(RuntimeError):
        await r.befehl("ton_testen")
    with pytest.raises(ValueError):
        await r.befehl("rm -rf")


async def test_startet_mit_spiel_und_endet_beim_abschalten(tmp_path):
    spiel_an = True
    r = radar(tmp_path, spiel_laeuft=spiel(lambda: spiel_an), abfrage_s=0.05, nachlauf_s=0.2)
    aufgabe = asyncio.create_task(r.watch())
    await warten_bis(lambda: r.laeuft and r.aufnahme)
    await r.befehl("ton_testen")
    await r.speichern({"ton": False})  # schickt neu_laden
    await warten_bis(lambda: (tmp_path / "befehle.txt").exists()
                     and (tmp_path / "befehle.txt").read_text() == "ton_testen\nneu_laden\n")
    spiel_an = False
    await warten_bis(lambda: not r.laeuft)
    spiel_an = True
    await warten_bis(lambda: r.laeuft)
    prozess = r.prozess
    aufgabe.cancel()  # Modul aus
    with pytest.raises(asyncio.CancelledError):
        await aufgabe
    assert prozess.returncode is not None and not r.laeuft and not r.aufnahme


async def test_neustart(tmp_path):
    r = radar(tmp_path, spiel_laeuft=spiel(lambda: True), abfrage_s=0.05)
    aufgabe = asyncio.create_task(r.watch())
    await warten_bis(lambda: r.laeuft)
    alt = r.prozess
    await r.befehl("neustart")
    assert r.laeuft and r.prozess is not alt and alt.returncode is not None
    aufgabe.cancel()
    with pytest.raises(asyncio.CancelledError):
        await aufgabe
