"""DPS-Feed gegen einen nachgebauten Overlay-Server des A2Tools-Meters."""
import asyncio
import json
from pathlib import Path

import jsonschema
from aiohttp import web

from deckbar_daemon import dps as dps_mod
from deckbar_daemon.config import Layout
from deckbar_daemon.dps import DpsFeed, DpsSettings, compact, read_a2tools
from deckbar_daemon.state import State

SCHEMA = json.loads((Path(__file__).parents[2] / "docs" / "protocol.schema.json").read_text())

SNAP = {
    "v": 1, "target": "Boss", "mode": "bossTargets", "timeMs": 83500, "hp": 42.57,
    "rows": [
        {"name": "Aria", "cls": "spiritmaster", "dps": 18432, "dmg": 1529856, "pct": 31.24, "you": True},
        {"name": "#1234", "cls": None, "dps": 900.7, "dmg": 1000, "pct": 0.1, "you": False},
        {"name": "Odd", "cls": "unbekannt", "dps": -5, "dmg": "x", "pct": None},
    ],
}


def test_compact():
    c = compact(SNAP)
    assert c["target"] == "Boss" and c["time"] == 83 and c["hp"] == 42.6
    assert c["rows"][0] == {"name": "Aria", "cls": "spiritmaster", "dps": 18432, "dmg": 1529856, "pct": 31.2, "you": True}
    assert c["rows"][1]["dps"] == 900
    assert c["rows"][2] == {"name": "Odd", "cls": None, "dps": 0, "dmg": 0, "pct": 0.0, "you": False}
    assert len(compact({"rows": [SNAP["rows"][0]] * 12})["rows"]) == 8
    jsonschema.validate({"v": 1, "type": "state", "values": {"dps": c, "dps_active": True}}, SCHEMA)


def test_read_a2tools(tmp_path):
    p = tmp_path / "settings.json"
    assert read_a2tools(p)["installed"] is False
    p.write_text(json.dumps({"dpsMeter.streamOverlay": "true", "dpsMeter.streamOverlayPort": "19000",
                             "dpsMeter.streamOverlayKey": "k" * 24}))
    assert read_a2tools(p) == {"installed": True, "enabled": True, "port": 19000, "key": "k" * 24}
    p.write_text("{kaputt")
    assert read_a2tools(p)["enabled"] is False


def test_dps_item_validation():
    Layout.model_validate({"pages": [{"id": "a", "items": [{"id": "d", "type": "dps", "players": 5, "extra": "dmg"}]}]})
    try:
        Layout.model_validate({"pages": [{"id": "a", "items": [{"id": "b", "players": 5}]}]})
    except ValueError as e:
        assert "players" in str(e)
    else:
        raise AssertionError("players bei button müsste abgelehnt werden")


async def fake_meter(key: str, frames: asyncio.Queue) -> tuple[web.AppRunner, int]:
    async def events(request: web.Request) -> web.StreamResponse:
        if request.query.get("key") != key:
            return web.Response(status=403, text="forbidden")
        resp = web.StreamResponse(headers={"Content-Type": "text/event-stream; charset=utf-8"})
        await resp.prepare(request)
        await resp.write(b"retry: 2000\n\n")
        while True:
            snap = await frames.get()
            if snap is None:
                break
            await resp.write(f"data: {json.dumps(snap)}\n\n".encode())
        return resp

    app = web.Application()
    app.router.add_get("/overlay/events", events)
    runner = web.AppRunner(app)
    await runner.setup()
    site = web.TCPSite(runner, "127.0.0.1", 0)
    await site.start()
    return runner, site._server.sockets[0].getsockname()[1]


async def wait_for(cond, timeout=3.0):
    for _ in range(int(timeout / 0.02)):
        if cond():
            return
        await asyncio.sleep(0.02)
    raise AssertionError("Bedingung nicht erreicht")


async def test_stream_combat_and_bad_key(tmp_path, monkeypatch):
    monkeypatch.setattr(dps_mod, "RETRY_S", 0.05)
    frames: asyncio.Queue = asyncio.Queue()
    runner, port = await fake_meter("geheim", frames)
    combat: list[bool] = []

    async def on_combat(active: bool) -> None:
        combat.append(active)

    state = State()
    feed = DpsFeed(state, tmp_path, on_combat)
    feed.save(DpsSettings(source="manual", port=port, key="falsch", return_after=1))
    task = asyncio.ensure_future(feed.watch())
    try:
        await wait_for(lambda: feed.status == "bad_key")
        assert state.values.get("dps") is None
        assert "falsch" not in json.dumps(feed.info())

        feed.save(DpsSettings(source="manual", port=port, key="geheim", return_after=1))
        await wait_for(lambda: feed.status == "connected")
        # erster Stand = alter Kampf, zählt nicht als Kampfbeginn
        await frames.put(SNAP)
        await wait_for(lambda: state.values.get("dps") is not None)
        assert state.values["dps_active"] is False and combat == []
        # neuer Schaden → Kampfbeginn
        more = json.loads(json.dumps(SNAP))
        more["rows"][0]["dmg"] += 5000
        await frames.put(more)
        await wait_for(lambda: state.values.get("dps_active") is True)
        assert combat == [True]
        # 1 s ohne neuen Schaden → Kampfende
        await wait_for(lambda: combat == [True, False], timeout=4)
        assert state.values["dps_active"] is False
        assert (tmp_path / "dps.yaml").stat().st_mode & 0o777 == 0o600
    finally:
        task.cancel()
        await frames.put(None)
        await runner.cleanup()


async def test_meter_not_running(tmp_path):
    import socket
    with socket.socket() as s:  # freien Port holen, auf dem dann niemand lauscht
        s.bind(("127.0.0.1", 0))
        port = s.getsockname()[1]
    feed = DpsFeed(State(), tmp_path)
    feed.save(DpsSettings(source="manual", port=port, key="x"))
    task = asyncio.ensure_future(feed.watch())
    try:
        await wait_for(lambda: feed.status == "no_meter")
    finally:
        task.cancel()


class FakeWS:
    closed = False

    def __init__(self) -> None:
        self.sent: list[dict] = []

    async def send_str(self, text: str) -> None:
        self.sent.append(json.loads(text))


async def test_auto_page(tmp_path):
    from deckbar_daemon.config import Settings
    from deckbar_daemon.server import NexBoard, Device

    deck = NexBoard(Settings(token="testtoken-123"), tmp_path)
    deck.layout = Layout.model_validate({"pages": [{"id": "main", "items": []},
                                                   {"id": "aion", "items": [{"id": "d", "type": "dps", "h": 2}]}]})
    deck.dps.settings = DpsSettings(auto_page="aion", return_after=5)
    ws = FakeWS()
    dev = Device(ws=ws, remote="test", page="main")
    deck.devices.add(dev)

    await deck._on_combat(True)
    assert ws.sent[-1] == {"v": 1, "type": "goto", "page": "aion"}
    jsonschema.validate(ws.sent[-1], SCHEMA)
    dev.page = "aion"  # Gerät meldet page_change
    await deck._on_combat(False)
    assert ws.sent[-1]["page"] == "main" and len(ws.sent) == 2
    dev.page = "main"

    # während des Kampfs selbst weggewischt → bleibt dort, auch nach dem Kampf
    await deck._on_combat(True)
    dev.page = "main"
    await deck._on_combat(False)
    assert len(ws.sent) == 3

    # ohne Kampf auf die DPS-Seite gewischt oder dort verbunden → erste Seite
    dev.page = "aion"
    await deck._follow_combat(dev)
    assert ws.sent[-1]["page"] == "main" and len(ws.sent) == 4

    # im Kampf schon auf der DPS-Seite → kein goto
    deck.state.update(dps_active=True)
    await deck._on_combat(True)
    await deck._follow_combat(dev)
    assert len(ws.sent) == 4


async def test_reset_button(tmp_path):
    from deckbar_daemon.config import Settings
    from deckbar_daemon.server import NexBoard

    deck = NexBoard(Settings(token="testtoken-123"), tmp_path)
    deck.layout = Layout.model_validate({"pages": [{"id": "aion", "items": [{"id": "d", "type": "dps", "h": 2}]}]})
    sent = []

    async def request(cmd, **args):
        sent.append(cmd)

    deck.dps.capture.request = request
    msg = {"v": 1, "type": "event", "event": "button_press", "item": "d", "part": "reset"}
    jsonschema.validate(msg, SCHEMA)

    deck.dps.settings = DpsSettings(source="capture")
    assert await deck.handle_event(msg, "test") is None
    assert sent == ["reset"]

    # Stream-Overlay des Meters: kein Reset möglich, nur Warnung
    deck.dps.settings = DpsSettings(source="auto")
    assert await deck.handle_event(msg, "test") is None
    assert sent == ["reset"]
