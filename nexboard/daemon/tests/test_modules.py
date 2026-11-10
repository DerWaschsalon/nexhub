"""Module: Speichern, Abhängigkeiten, Aufgaben zur Laufzeit starten und stoppen; Web-API."""
import pytest
import yaml
from aiohttp.test_utils import TestClient, TestServer

from deckbar_daemon.app import NexBoard, build_app
from deckbar_daemon.config import Settings


def board(tmp_path) -> NexBoard:
    return NexBoard(Settings(token="testtoken123", mdns=False, usb="off"), tmp_path, mdns=False)


def test_dependency_graph(tmp_path):
    m = board(tmp_path).modules
    assert m.requirements("discord.bot") == {"aion2.dps"}
    assert {"aion2.overlay", "aion2.runs", "discord.bot"} <= m.dependents("aion2.dps")
    assert m.dependents("deck") == set()
    assert m.requirements("aion2.radar") == {"aion2.schedule"}  # Feldbosse stehen unter Termine
    assert m.requirements("aion2.plugins") == {"aion2.overlay", "aion2.dps"}
    assert m.order == ["deck", "aion2.dps", "aion2.overlay", "aion2.plugins", "aion2.runs", "aion2.schedule",
                       "aion2.radar", "discord.bot", "hub", "updates"]
    for mid, info in m.infos.items():
        assert all(r in m.infos for r in info.requires), mid


def test_load_and_first_start(tmp_path):
    assert board(tmp_path).modules.enabled == {"deck", "updates"}  # frische Installation
    assert yaml.safe_load((tmp_path / "modules.yaml").read_text())["enabled"] == ["deck", "updates"]
    (tmp_path / "modules.yaml").write_text("enabled: [aion2.overlay, gibts-nicht]\n")
    # Abhängigkeit kommt dazu; Plugins liefen bisher mit dem Overlay und sind jetzt ein eigenes Modul
    assert board(tmp_path).modules.enabled == {"aion2.overlay", "aion2.dps", "aion2.plugins"}


@pytest.fixture
async def client(tmp_path, monkeypatch):
    # nie an ein echtes, laufendes Overlay schicken (dessen Socket liegt im Laufzeitordner)
    import deckbar_daemon.overlay as overlay_mod
    monkeypatch.setattr(overlay_mod, "socket_path", lambda: tmp_path / "kein-overlay.sock")
    (tmp_path / "modules.yaml").write_text("enabled: [deck]\n")
    deck = board(tmp_path)
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


async def test_api_module_settings(client):
    r = await client.get("/api/m/aion2.dps/settings")
    body = await r.json()
    assert r.status == 200 and body["schema"]["title"] == "DpsSettings" and body["settings"]["source"] == "capture"
    r = await client.put("/api/m/aion2.dps/settings", json={"key": "geheim", "return_after": 30})
    body = await r.json()
    assert body["settings"]["key"] == "••••••••" and body["settings"]["return_after"] == 30
    assert client.deck.dps.settings.key == "geheim"  # Komponente hat den neuen Stand
    r = await client.put("/api/m/aion2.dps/settings", json={"key": "••••••••", "return_after": 5})
    assert client.deck.dps.settings.key == "geheim"  # Punkte zurück: Schlüssel bleibt
    assert (await client.put("/api/m/aion2.dps/settings", json={"return_after": -1})).status == 422
    assert (await client.get("/api/m/updates/settings")).status == 404  # Updates: keine Einstellungen
    r = await client.put("/api/m/deck/settings", json={"auto_page": "main"})
    assert (await r.json())["settings"]["auto_page"] == "main"
    assert (await client.get("/api/m/gibts-nicht/settings")).status == 404


async def test_api_plugins_nur_verwalten(client):
    r = await client.post("/api/plugins", json={"cmd": "plugin_list"})
    assert r.status == 200 and "builtIn" in (await r.json())["result"]
    # Was eine Plugin-Seite darf (Daten lesen, Fenster steuern), darf die Web-UI nicht
    r = await client.post("/api/plugins", json={"cmd": "plugin_storage_get", "args": {}})
    assert r.status == 400
    r = await client.get("/api/plugins/texts")
    assert r.status == 200 and "permStorage" in await r.json()
