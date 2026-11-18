"""Modul Leveling-Guide: reagiert auf Client.txt, bittet um seine Leisten-Seite, nimmt Tippen auf der Kachel an."""
import asyncio

import pytest
from aiohttp.test_utils import TestClient, TestServer

from deckbar_daemon.app import NexBoard, build_app
from deckbar_daemon.config import Layout, Settings
from deckbar_daemon.core.topics import GAME_STARTED, GAME_STOPPED, POE_LOG, TILE_EVENT, TileEvent
from deckbar_daemon.poe.client_log import ZoneEntered
from deckbar_daemon.poe.session import PoeLogMessage

TOKEN = "testtoken123"


@pytest.fixture
async def client(tmp_path, monkeypatch):
    import deckbar_daemon.overlay as overlay_mod
    monkeypatch.setattr(overlay_mod, "socket_path", lambda: tmp_path / "kein-overlay.sock")
    (tmp_path / "modules.yaml").write_text("enabled: [deck]\n")
    deck = NexBoard(Settings(token=TOKEN, mdns=False, usb="off"), tmp_path, mdns=False)
    deck.overlay.manage_unit = False
    deck.bar.active = True
    deck.bar.layout.set(Layout.model_validate({"pages": [
        {"id": "main", "items": [{"id": "b", "label": "x"}]},
        {"id": "poe", "items": [{"id": "g", "type": "guide", "w": 6, "h": 2}]},
    ]}), save=False)
    module = next(m for m in deck.web_modules if m.info.id == "poe1.leveling")
    module.game_state = FakeGame()
    await module.activate()  # ohne poe1.client: kein Blick in /proc
    async with TestClient(TestServer(build_app(deck))) as c:
        c.deck, c.module = deck, module
        yield c


class FakeGame:
    def __init__(self):
        self.running = False
        self.zone = None
        self.levels = {}


async def connect(client):
    ws = await client.ws_connect("/ws")
    await ws.send_json({"v": 1, "type": "hello", "token": TOKEN, "page": "main",
                        "device": {"id": "t", "width": 640, "height": 172}})
    while (await ws.receive_json())["type"] != "state":
        pass
    return ws


async def next_goto(ws):
    while True:
        msg = await ws.receive_json(timeout=1)
        if msg["type"] == "goto":
            return msg["page"]


async def test_zone_advances_and_page_follows_game(client):
    bus, module = client.deck.bus, client.module
    ws = await connect(client)
    assert client.deck.state.values["guide"]["step"].startswith("1/")
    await bus.emit(POE_LOG, PoeLogMessage("poe1", ZoneEntered("1_1_town", 1)))
    assert module.leveling.tracker.progress == 1  # Ziel „Lioneye's Watch“ betreten
    await bus.emit(POE_LOG, PoeLogMessage("poe2", ZoneEntered("1_1_2", 1)))  # anderes Spiel: nichts
    assert module.leveling.tracker.progress == 1

    module.game_state.running = True
    await bus.emit(GAME_STARTED, "poe1")
    assert await next_goto(ws) == "poe"
    await ws.send_json({"v": 1, "type": "event", "event": "page_change", "page": "poe"})  # Gerät ist umgeblättert
    while client.deck.bar.devices.info()[0]["page"] != "poe":
        await asyncio.sleep(0.01)
    module.game_state.running = False
    await bus.emit(GAME_STOPPED, "poe1")
    assert await next_goto(ws) == "main"
    await ws.close()


async def test_tile_and_web_commands(client):
    bus, module = client.deck.bus, client.module
    await bus.emit(TILE_EVENT, TileEvent("guide", "g", "button_press", "next"))
    assert module.leveling.tracker.progress == 1
    await bus.emit(TILE_EVENT, TileEvent("guide", "g", "button_press", "back"))
    assert module.leveling.tracker.progress == 0
    r = await client.post("/api/poe1/leveling/command", json={"cmd": "skip"})
    assert (await r.json())["message"]  # ohne bekannte Zone geht der Schnellvorlauf nicht
    assert (await client.post("/api/poe1/leveling/command", json={"cmd": "x"})).status == 400
    assert (await client.post("/api/poe1/leveling/import", json={"code": "kaputt"})).status == 422
    r = await client.get("/api/poe1/leveling")
    assert (await r.json())["lines"][0]["segments"]


async def test_skip_lands_in_zone_then_moves_on_while_playing(client, monkeypatch):
    import deckbar_daemon.modules.poe_leveling as module_file
    monkeypatch.setattr(module_file, "ZONE_CHECK_S", 0.01)
    module = client.module
    await client.deck.bus.emit(POE_LOG, PoeLogMessage("poe1", ZoneEntered("1_1_4_1", 5, live=False)))
    await client.post("/api/poe1/leveling/command", json={"cmd": "skip"})
    landed = module.leveling.tracker.progress
    assert module.leveling.tracker.target_area == "1_1_4_1"
    module.game_state.running = True  # erst im Spiel geht es von selbst weiter (wie die Log-Schleife im Original)
    module.spawn(module._watch_zone)
    await asyncio.sleep(0.1)
    # eine Seite weiter; Ligastart-Seiten dazwischen gelten nicht und werden übersprungen
    assert module.leveling.tracker.progress > landed and module.leveling.tracker.target_area != "1_1_4_1"
