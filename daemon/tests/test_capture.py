"""capture.py: Programm mit dem Spiel starten und beenden, Zeilen auswerten. Statt deckbar-capture
läuft ein kleines Python-Skript mit demselben Zeilenformat."""
import asyncio
import sys
import textwrap

import pytest

from deckbar_daemon import capture
from deckbar_daemon.capture import Capture, is_aion2_process
from deckbar_daemon.dps import compact

FAKE = textwrap.dedent('''\
    import json, sys
    def out(o):
        print(json.dumps(o), flush=True)
    out({"type": "hello", "version": "0", "parser": "x", "cap_net_raw": CAPS})
    out({"type": "status", "port": 7777, "ping": 21})
    out({"type": "dps", "view": {"target": "Boss", "mode": "bossTargets", "timeMs": 4000, "hp": 50.0,
         "targetId": 9, "boss": True,
         "rows": [{"id": 1, "name": "Alpha", "cls": "cleric", "dps": 10, "dmg": 40, "pct": 100.0, "you": True}]}})
    for line in sys.stdin:
        cmd = json.loads(line)
        out({"type": "reply", "id": cmd["id"], "ok": cmd["cmd"] != "kaputt", "result": cmd["cmd"], "error": "nö"})
    out({"type": "fights_saved", "ids": ["f1"]})
    out({"type": "bye"})
''')


def fake_binary(tmp_path, caps=True):
    p = tmp_path / "deckbar-capture"
    p.write_text(f"#!{sys.executable}\n" + FAKE.replace("CAPS", "True" if caps else "False"))
    p.chmod(0o755)
    return str(p)


def test_is_aion2_process():
    assert is_aion2_process("AION2.exe\n", b"")
    assert is_aion2_process("wine64-preload", b"Z:\\Games\\Binaries\\Win64\\AION2.exe\0-x")
    assert not is_aion2_process("bash", b"/bin/bash\0-c\0AION2.exe")
    assert not is_aion2_process("AION2Launcher", b"")


async def _until(pred, timeout=5.0):
    loop = asyncio.get_running_loop()
    end = loop.time() + timeout
    while not pred():
        assert loop.time() < end, "Zeitüberschreitung"
        await asyncio.sleep(0.02)


async def test_lebenszyklus(tmp_path, monkeypatch):
    monkeypatch.setattr(capture, "GAME_POLL_S", 0.05)
    monkeypatch.setattr(capture, "STOP_AFTER_S", 0.1)
    monkeypatch.setenv("XDG_DATA_HOME", str(tmp_path))
    views, fights = [], []
    game = {"on": False}

    async def on_view(v, first):
        views.append((v, first))

    async def on_fights(ids):
        fights.extend(ids)

    async def nothing():
        pass

    cap = Capture(on_view, nothing, on_fights)
    cap.game_running = lambda: game["on"]
    job = asyncio.ensure_future(cap.run(fake_binary(tmp_path)))
    try:
        await _until(lambda: cap.phase == "no_game")
        game["on"] = True
        await _until(lambda: cap.phase == "running" and views)
        v, first = views[0]
        assert first and compact(v)["rows"][0]["name"] == "Alpha" and compact(v)["hp"] == 50.0
        assert cap.info()["port"] == 7777 and cap.info()["cap_net_raw"] is True

        assert await cap.request("history") == "history"
        with pytest.raises(RuntimeError, match="nö"):
            await cap.request("kaputt")

        # Spiel beendet: Eingabe zu, Programm speichert, Anzeige wird geleert
        game["on"] = False
        await _until(lambda: not cap.running and views[-1] == (None, False))
        assert fights == ["f1"]
        await _until(lambda: cap.phase == "no_game" or cap.phase == "running")
    finally:
        job.cancel()
        await asyncio.gather(job, return_exceptions=True)


async def test_ohne_rechte(tmp_path, monkeypatch):
    monkeypatch.setattr(capture, "GAME_POLL_S", 0.05)
    monkeypatch.setenv("XDG_DATA_HOME", str(tmp_path))

    async def nothing(*a):
        pass

    cap = Capture(nothing, nothing)
    cap.game_running = lambda: True
    job = asyncio.ensure_future(cap.run(fake_binary(tmp_path, caps=False)))
    try:
        await _until(lambda: cap.phase == "no_caps")
    finally:
        job.cancel()
        await asyncio.gather(job, return_exceptions=True)
    assert not cap.running


async def test_kein_programm(tmp_path, monkeypatch):
    monkeypatch.setattr(capture, "GAME_POLL_S", 0.05)

    async def nothing(*a):
        pass

    cap = Capture(nothing, nothing)
    job = asyncio.ensure_future(cap.run(str(tmp_path / "fehlt")))
    try:
        await _until(lambda: cap.phase == "no_binary")
    finally:
        job.cancel()
        await asyncio.gather(job, return_exceptions=True)
