"""Verkehr zum Gerät: DPS gedrosselt und nur bei sichtbarer Kachel, Binärbilder, Cover nicht doppelt."""
import asyncio
import json
import struct

import pytest
from aiohttp import WSMsgType
from aiohttp.test_utils import TestClient, TestServer

import deckbar_daemon.server as server_mod
from deckbar_daemon.art import bin_chunks
from deckbar_daemon.config import Layout, Settings
from deckbar_daemon.server import NexBoard, build_app
from deckbar_daemon.usb import _text_only

TOKEN = "testtoken123"


def test_bin_chunks_header_and_rows():
    data = bytes(range(256)) * (640 * 172 * 2 // 256)
    frames = bin_chunks(b"b", "abc123", 640, 172, data)
    assert len(frames) == 172 // 9 + 1  # 9 Zeilen à 1280 Byte pro Frame
    got = b""
    for f in frames:
        magic, kind, idb, w, h, y, rows = struct.unpack("<2sc16sHHHH", f[:27])
        assert (magic, kind, idb.rstrip(b"\0"), w, h) == (b"DB", b"b", b"abc123", 640, 172)
        assert len(f) == 27 + rows * w * 2 <= 27 + 12000
        assert y * 1280 == len(got)
        got += f[27:]
    assert got == data


def test_usb_bridge_strips_binary_cap():
    hello = json.dumps({"v": 1, "type": "hello", "caps": ["bin", "x"], "token": "t"})
    assert json.loads(_text_only(hello))["caps"] == ["x"]
    other = '{"v":1,"type":"event","event":"tap","item":"bin"}'
    assert _text_only(other) == other


@pytest.fixture
async def client(tmp_path, monkeypatch):
    import deckbar_daemon.overlay as overlay_mod
    monkeypatch.setattr(overlay_mod, "socket_path", lambda: tmp_path / "kein-overlay.sock")
    monkeypatch.setattr(server_mod, "DPS_DEVICE_INTERVAL", 0.3)
    (tmp_path / "modules.yaml").write_text("enabled: [deck]\n")
    deck = NexBoard(Settings(token=TOKEN, mdns=False, usb="off"), tmp_path, mdns=False)
    deck.overlay.manage_unit = False
    deck.layout = Layout.model_validate({"pages": [
        {"id": "main", "items": [{"id": "b", "label": "x"}]},
        {"id": "aion", "items": [{"id": "d", "type": "dps", "players": 3, "w": 6, "h": 2}]},
    ]})
    deck.layout_payload = deck.layout.device_payload()
    async with TestClient(TestServer(build_app(deck))) as c:
        c.deck = deck
        yield c


async def connect(client, page, caps=None):
    ws = await client.ws_connect("/ws")
    hello = {"v": 1, "type": "hello", "token": TOKEN, "page": page,
             "device": {"id": "t", "width": 640, "height": 172}}
    if caps is not None:
        hello["caps"] = caps
    await ws.send_json(hello)
    while (await ws.receive_json())["type"] != "state":  # welcome, layout, state (full)
        pass
    return ws


async def drain(ws, timeout=0.15):
    out = []
    while True:
        try:
            m = await ws.receive(timeout=timeout)
        except TimeoutError:
            return out
        out.append(m)


def dps_value(n):
    return {"target": "Boss", "time": n, "hp": 50.0,
            "rows": [{"name": f"P{i}", "cls": None, "dps": 100 - i, "dmg": 1, "pct": 10.0, "you": False}
                     for i in range(8)]}


async def test_dps_throttled_trimmed_and_only_on_dps_page(client):
    deck = client.deck
    ws_dps = await connect(client, "aion")
    ws_main = await connect(client, "main")
    for n in range(10):  # 10 Updates in 0,1 s
        deck.state.update(dps=dps_value(n))
        await asyncio.sleep(0.01)
    await asyncio.sleep(0.5)
    got = [json.loads(m.data) for m in await drain(ws_dps)]
    dps_msgs = [m["values"]["dps"] for m in got if m["type"] == "state" and "dps" in m["values"]]
    assert 1 <= len(dps_msgs) <= 2  # gedrosselt, nicht 10
    assert dps_msgs[-1]["time"] == 9  # der letzte Stand kommt an
    assert len(dps_msgs[-1]["rows"]) == 3  # nur so viele Zeilen wie die Kachel zeigt
    assert not [m for m in await drain(ws_main) if "dps" in json.loads(m.data).get("values", {})]

    # Wechsel auf die DPS-Seite: aktueller Stand kommt sofort
    await ws_main.send_json({"v": 1, "type": "event", "event": "page_change", "page": "aion"})
    got = [json.loads(m.data) for m in await drain(ws_main, 0.3)]
    assert any(m.get("values", {}).get("dps", {}).get("time") == 9 for m in got)
    await ws_dps.close()
    await ws_main.close()


async def test_images_binary_and_cover_not_resent(client):
    deck = client.deck
    deck.bg.id, deck.bg.data = "bg1", bytes(640 * 172 * 2)
    ws = await connect(client, "main", caps=["bin"])
    frames = [m for m in await drain(ws, 0.3) if m.type == WSMsgType.BINARY]
    assert len(frames) == 20 and frames[0].data[:3] == b"DBb"  # statt 172 JSON-Teilen

    async def render(size):
        return "cov1", bytes(size * size * 2)
    deck.art.render = render
    await ws.send_json({"v": 1, "type": "art_request", "size": 88})
    frames = [m for m in await drain(ws) if m.type == WSMsgType.BINARY]
    assert frames and frames[0].data[:3] == b"DBa"
    await ws.send_json({"v": 1, "type": "art_request", "size": 88, "have": "cov1"})
    assert not await drain(ws)  # hat es schon
    await ws.close()

    old = await connect(client, "main")  # alte Firmware: JSON wie bisher
    msgs = [json.loads(m.data) for m in await drain(old, 0.3) if m.type == WSMsgType.TEXT]
    assert sum(1 for m in msgs if m["type"] == "bg") == 172 // (2000 // 1280)
    await old.close()
