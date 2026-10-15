"""Module: Speichern, Abhängigkeiten, Aufgaben zur Laufzeit starten und stoppen; Web-API."""
import asyncio

import pytest
import yaml
from aiohttp.test_utils import TestClient, TestServer

from deckbar_daemon.config import Settings
from deckbar_daemon.modules import MODULES, ModuleManager, dependents, requirements
from deckbar_daemon.server import DeckBar, build_app


def test_dependency_graph():
    assert requirements("discord.bot") == {"aion2.dps"}
    assert {"aion2.overlay", "aion2.runs", "discord.bot"} <= dependents("aion2.dps")
    assert dependents("deck") == set()
    ids = [m.id for m in MODULES]
    assert len(ids) == len(set(ids))
    for m in MODULES:
        assert all(r in ids for r in m.requires)


def test_load_save_and_defaults(tmp_path):
    m = ModuleManager(tmp_path)
    assert m.enabled == {"deck", "updates"}
    assert yaml.safe_load((tmp_path / "modules.yaml").read_text()) == {"enabled": ["deck", "updates"]}
    (tmp_path / "modules.yaml").write_text("enabled: [aion2.overlay, gibts-nicht]\n")
    assert ModuleManager(tmp_path).enabled == {"aion2.overlay", "aion2.dps"}  # Abhängigkeit kommt dazu
    (tmp_path / "modules.yaml").write_text("kaputt: [")
    assert ModuleManager(tmp_path, lambda: {"deck"}).enabled == {"deck"}


async def test_runtime_start_stop_and_hooks(tmp_path):
    m = ModuleManager(tmp_path, lambda: {"deck"})
    runs = {"dps": 0, "hooks": []}

    async def dps_task():
        runs["dps"] += 1
        await asyncio.Event().wait()

    async def hook(on):
        runs["hooks"].append(on)

    m.register("aion2.dps", dps_task, hook=hook, status=lambda: {"x": 1})
    await m.start()
    assert runs["dps"] == 0
    changed = await m.set("discord.bot", True)
    assert changed == ["aion2.dps", "discord.bot"]
    await asyncio.sleep(0)
    assert runs["dps"] == 1 and runs["hooks"] == [True]
    info = {x["id"]: x for x in m.info()["modules"]}
    assert info["aion2.dps"]["status"] == {"x": 1} and info["discord.bot"]["enabled"]
    assert await m.set("aion2.dps", False) == ["aion2.dps", "discord.bot"]  # Abhängige gehen mit
    assert runs["hooks"] == [True, False] and not m.runtime["aion2.dps"].running
    assert ModuleManager(tmp_path).enabled == {"deck"}
    await m.stop_all()
    with pytest.raises(KeyError):
        await m.set("nope", True)


async def test_crashed_task_restarts(tmp_path, monkeypatch):
    import deckbar_daemon.modules as mod
    calls = []

    async def flaky():
        calls.append(1)
        if len(calls) == 1:
            raise RuntimeError("kaputt")
        await asyncio.Event().wait()

    real_sleep = asyncio.sleep
    monkeypatch.setattr(mod.asyncio, "sleep", lambda s: real_sleep(0))
    m = ModuleManager(tmp_path, lambda: {"updates"})
    m.register("updates", flaky)
    await m.start()
    for _ in range(5):
        await real_sleep(0)
    assert len(calls) == 2
    await m.stop_all()


@pytest.fixture
async def client(tmp_path):
    (tmp_path / "modules.yaml").write_text("enabled: [deck]\n")
    deck = DeckBar(Settings(token="testtoken123", mdns=False, usb="off"), tmp_path, mdns=False)
    deck.overlay.manage_unit = False
    async with TestClient(TestServer(build_app(deck))) as c:
        c.deck = deck
        yield c


async def test_api_modules_and_settings(client):
    r = await client.get("/api/modules")
    data = await r.json()
    assert {m["id"] for m in data["modules"] if m["enabled"]} == {"deck"}
    r = await client.put("/api/modules/aion2.overlay", json={"enabled": True})
    data = await r.json()
    assert data["changed"] == ["aion2.dps", "aion2.overlay"]
    assert (await client.put("/api/modules/x", json={"enabled": True})).status == 404
    assert (await client.put("/api/modules/deck", json={"enabled": "ja"})).status == 400

    r = await client.get("/api/settings")
    s = await r.json()
    assert s["settings"]["token"] == "••••••••"
    r = await client.put("/api/settings", json={"name": "Pult", "port": 9000, "token": "••••••••"})
    s = await r.json()
    assert r.status == 200 and s["restart"] == ["port"]
    assert client.deck.settings.name == "Pult" and client.deck.settings.port == 8765  # Port erst nach Neustart
    saved = yaml.safe_load((client.deck.config_dir / "config.yaml").read_text())
    assert saved["port"] == 9000 and saved["token"] == "testtoken123"
    assert (await client.put("/api/settings", json={"port": 70000})).status == 422
    assert (await (await client.post("/api/settings/token")).json())["token"] == "testtoken123"


async def test_api_bot_and_overlay(client):
    r = await client.put("/api/bot", json={"dps_enabled": True, "dps_url": "http://127.0.0.1:1/dps/x"})
    assert r.status == 200 and (await r.json())["settings"]["dps_url"] == "••••••••"
    assert (await client.put("/api/bot", json={"dps_url": "nix"})).status == 422
    assert (await client.post("/api/bot/test/dps")).status == 409  # Modul aus
    r = await client.put("/api/overlay", json={"fx": "brennen", "widgets": {"meter": {"x": 10, "y": 20}}})
    o = await r.json()
    assert o["layout"]["fx"] == "brennen" and o["layout"]["widgets"]["meter"]["x"] == 10
    assert o["layout"]["widgets"]["boss"]["enabled"]  # Rest bleibt
    assert (await client.put("/api/overlay", json={"fx": "regenbogen"})).status == 422
    r = await client.post("/api/overlay/command", json={"cmd": "edit"})
    assert r.status == 409  # Programm läuft nicht (kein Socket)


async def test_device_rejected_when_deck_off(client):
    await client.deck.modules.set("deck", False)
    ws = await client.ws_connect("/ws")
    await ws.send_json({"v": 1, "type": "hello", "token": "testtoken123", "device": {"id": "x"}})
    msg = await ws.receive_json()
    assert msg["type"] == "error" and msg["code"] == "disabled"
    await ws.close()
