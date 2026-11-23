"""updates.py: Versionsvergleich, Commits hinter dem Upstream, A2Tools-Release."""
import subprocess

from deckbar_daemon.updates import Updates, version_tuple


def test_version_tuple():
    assert version_tuple("v2.0.62") == (2, 0, 62)
    assert version_tuple("v2.0.62") < version_tuple("v2.0.100") < version_tuple("v2.1.0")
    assert version_tuple("2.0.62-1-gabc") == (2, 0, 62)
    assert version_tuple(None) == () and version_tuple("main") == ()


def git(cwd, *args):
    subprocess.run(["git", "-C", str(cwd), *args], check=True, capture_output=True)


def commit(repo, path, msg):
    f = repo / path
    f.parent.mkdir(parents=True, exist_ok=True)
    f.write_text(msg)
    git(repo, "add", path)
    git(repo, "commit", "-q", "-m", msg)


async def test_commits_hinter_upstream(tmp_path):
    origin, work, other = tmp_path / "origin.git", tmp_path / "work", tmp_path / "other"
    subprocess.run(["git", "init", "-q", "--bare", "-b", "main", str(origin)], check=True)
    for d in (work, other):
        subprocess.run(["git", "clone", "-q", str(origin), str(d)], check=True, capture_output=True)
        git(d, "config", "user.email", "t@example.invalid")
        git(d, "config", "user.name", "t")
    commit(work, "nexboard/a", "eins")
    git(work, "push", "-q", "origin", "HEAD:main")
    git(other, "pull", "-q", "origin", "main")
    git(other, "branch", "-u", "origin/main")
    commit(work, "nexboard/a", "zwei")
    commit(work, "nexboard/a", "drei")
    commit(work, "bot/b", "vier")  # anderer Teil des Monorepos: kein NexBoard-Update
    git(work, "push", "-q", "origin", "HEAD:main")

    up = Updates(other / "nexboard")

    async def kein_a2tools():
        return {"current": "v2.0.62", "latest": "v2.0.62", "newer": False}

    up._check_a2tools = kein_a2tools
    seen = []

    async def changed():
        seen.append(up.info())

    up.listeners.append(changed)
    await up.check()
    d = up.info()["deckbar"]
    assert d["behind"] == 2 and d["ahead"] == 0 and d["latest"] == "drei"
    assert up.info()["available"] and seen and up.info()["error"] == ""


async def test_neues_a2tools_release(tmp_path):
    up = Updates(tmp_path)

    async def repo():
        return {"behind": 0, "ahead": 0}

    async def a2():
        return {"current": "v2.0.62", "latest": "v2.0.63", "newer": True}

    up._check_repo, up._check_a2tools = repo, a2
    await up.check()
    assert up.info()["available"] and up.info()["a2tools"]["latest"] == "v2.0.63"


async def test_fehler_werden_gemeldet(tmp_path):
    up = Updates(tmp_path)  # kein Git-Repo, kein Submodul

    async def a2():
        raise RuntimeError("offline")

    up._check_a2tools = a2
    await up.check()
    info = up.info()
    assert not info["available"] and "NexBoard" in info["error"] and "offline" in info["error"]


async def test_ergebnis_uebersteht_neustart(tmp_path, monkeypatch):
    import json as _json

    from deckbar_daemon import updates as up_mod
    path = tmp_path / "updates-state.json"
    up = Updates(tmp_path, state_path=path)

    async def local():
        return "abc|v1"
    up._local = local

    async def nichts():
        return {"behind": 0}
    up._check_repo = up._check_a2tools = nichts
    await up.check()
    assert _json.loads(path.read_text())["local"] == "abc|v1"

    again = Updates(tmp_path, state_path=path)
    again._local = local
    delay = await again._first_delay()
    assert delay > up_mod.CHECK_EVERY_S - 60 and again.state["checked_at"]  # nicht gleich wieder prüfen

    async def anders():
        return "def|v1"  # update.sh hat aktualisiert
    again._local = anders
    assert await again._first_delay() == up_mod.FIRST_CHECK_S


def test_firmware_stand_im_repo(tmp_path):
    from deckbar_daemon.updates import (
        FIRMWARE_CONFIG,
        firmware_in_repo,
        firmware_outdated,
    )

    assert version_tuple(firmware_in_repo()) >= (0, 9)  # liest die echte deckbar_config.h
    assert FIRMWARE_CONFIG.is_file()
    assert firmware_in_repo(tmp_path / "fehlt.h") is None
    assert firmware_outdated("0.8.1", "0.9.0") and not firmware_outdated("0.9.0", "0.9.0")
    assert not firmware_outdated("0.10.0", "0.9.0")  # neuer geflasht als das Repo
    assert not firmware_outdated("", "0.9.0") and not firmware_outdated("sim", "0.9.0")
    assert not firmware_outdated("0.8.1", None)


def updates_module(tmp_path, monkeypatch, firmware, web_url=None):
    from nexcore import Context, EventBus, Paths

    from deckbar_daemon.core.live import LiveHub
    from deckbar_daemon.modules import updates as module
    from deckbar_daemon.state import State

    monkeypatch.setattr(module, "firmware_in_repo", lambda: "0.9.1")
    state, bus = State(), EventBus()
    updates = Updates(tmp_path, tmp_path / "updates-state.json")
    m = module.UpdatesModule(Context(bus, Paths("test")), LiveHub(bus), updates, state, lambda: firmware, web_url)
    m.active = True
    return m, updates, state


async def test_update_hinweis_auf_der_leiste(tmp_path, monkeypatch):
    firmware = ["0.9.1"]
    m, updates, state = updates_module(tmp_path, monkeypatch, firmware)

    await m.announce()
    assert state.values["update_available"] is False and m.news() == []
    firmware.append("0.9.0")  # zweite Leiste mit alter Firmware verbunden
    await m.announce()
    assert state.values["update_available"] is True
    assert m.news() == ["Leiste: Firmware 0.9.0, neu 0.9.1 (selbst flashen)"]
    assert m.ui_info()["firmware"] == {"repo": "0.9.1", "outdated": ["0.9.0"]}  # Hinweis in der Web-UI
    firmware.pop()
    updates.state.update(deckbar={"behind": 3}, a2tools={"newer": True, "latest": "v2.0.96", "current": "v2.0.95"})
    await updates._changed()  # wie nach einer Prüfung
    assert m.news() == ["NexBoard: 3 neue Commits", "A2Tools v2.0.96 (bisher v2.0.95)"]
    await m.stop()  # Modul aus: kein Hinweis mehr auf der Leiste
    assert state.values["update_available"] is False


async def test_desktop_benachrichtigung_einmal_je_stand(tmp_path, monkeypatch):
    """notify-send und xdg-open als Skripte: der Knopf wird „geklickt“, die Web-UI geht auf."""
    import asyncio
    import os

    bin_dir, log = tmp_path / "bin", tmp_path / "aufrufe.txt"
    bin_dir.mkdir()
    for name, script in (("notify-send", f'echo "$@" >> {log}\necho open'), ("xdg-open", f'echo "xdg-open $1" >> {log}')):
        (bin_dir / name).write_text(f"#!/bin/sh\n{script}\n")
        (bin_dir / name).chmod(0o755)
    monkeypatch.setenv("PATH", f"{bin_dir}{os.pathsep}{os.environ['PATH']}")
    m, updates, _ = updates_module(tmp_path, monkeypatch, [], web_url=lambda: "http://localhost:8765/")

    updates.state["deckbar"] = {"behind": 1}
    await m.announce()
    await m._notice
    await m.announce()  # gleicher Stand: keine zweite Benachrichtigung
    for _ in range(100):  # xdg-open läuft losgelöst
        if "xdg-open" in log.read_text():
            break
        await asyncio.sleep(0.01)
    calls = log.read_text().splitlines()
    assert len([c for c in calls if "Update verfügbar" in c]) == 1
    assert "NexBoard: 1 neuer Commit" in calls[0] and "-A open=Updates anzeigen" in calls[0]
    assert calls[-1] == "xdg-open http://localhost:8765/#/updates"


async def test_ohne_web_url_keine_benachrichtigung(tmp_path, monkeypatch):
    m, updates, state = updates_module(tmp_path, monkeypatch, [])
    updates.state["deckbar"] = {"behind": 2}
    await m.announce()
    assert state.values["update_available"] is True and m._notice is None  # Testinstanz
