"""Plugin-Host: Katalog und Signatur, Installation, Ereignisse, Berechtigungen, Auslieferung."""
import asyncio
import hashlib
import json

import pytest
from aiohttp import web
from aiohttp.test_utils import TestClient, TestServer
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
from cryptography.hazmat.primitives.serialization import Encoding, PublicFormat

from deckbar_daemon.a2ui import A2Ui
from deckbar_daemon.plugins import PluginError, PluginHost, content_policy, newer, safe_path, take_ready, verify_catalog, Pending, valid_id


class FakeCapture:
    def __init__(self):
        self.data_listeners = []
        self.status = {}
        self.running = False
        self.full = False
        self.sent = []

    async def request(self, cmd, timeout=5, **args):
        self.sent.append((cmd, args))
        return {"errors": []}

    async def set_full(self, on):
        self.full = on


class Cdn:
    """Ein Katalog wie cdn.a2tools.app, signiert mit einem Testschlüssel."""

    def __init__(self):
        self.key = Ed25519PrivateKey.generate()
        self.key_hex = self.key.public_key().public_bytes(Encoding.Raw, PublicFormat.Raw).hex()
        self.files = {}
        self.serial = 100
        self.entries = []
        self.body = b""
        self.signature = b""

    def add(self, plugin="ping", version="1.0.0", permissions=("storage",), decoders=(), manifest_permissions=None, extra=None):
        manifest = {"id": plugin, "name": plugin.title(), "version": version, "apiVersion": 2,
                    "permissions": list(manifest_permissions if manifest_permissions is not None else permissions),
                    "decoders": list(decoders), "ui": {"panel": {"width": 320, "height": 400}}}
        files = {"manifest.json": json.dumps(manifest).encode(), "index.html": b"<html><head></head><body>hi</body></html>",
                 **(extra or {})}
        for path, data in files.items():
            self.files[f"/{plugin}/{version}/{path}"] = data
        self.entries = [e for e in self.entries if e["id"] != plugin]
        self.entries.append({"id": plugin, "name": plugin.title(), "version": version, "apiVersion": 2, "description": "d",
                             "author": "a", "permissions": list(permissions), "source": "s",
                             "files": {p: hashlib.sha256(d).hexdigest() for p, d in files.items()}})
        self.sign()

    def sign(self):
        self.body = json.dumps({"format": 1, "serial": self.serial, "plugins": self.entries}).encode()
        self.signature = self.key.sign(self.body).hex().encode()

    async def handle(self, request):
        if request.path == "/index.json":
            return web.Response(body=self.body)
        if request.path == "/index.json.sig":
            return web.Response(body=self.signature)
        if request.path in self.files:
            return web.Response(body=self.files[request.path])
        raise web.HTTPNotFound()


@pytest.fixture
async def cdn():
    c = Cdn()
    app = web.Application()
    app.router.add_get("/{tail:.*}", c.handle)
    server = TestServer(app)
    await server.start_server()
    c.url = str(server.make_url("")).rstrip("/")
    yield c
    await server.close()


@pytest.fixture
async def host(tmp_path, cdn):
    emitted = []
    settings = {}

    async def emit(event, payload):
        emitted.append((event, payload))

    def save(key, value):
        settings[key] = value

    h = PluginHost(FakeCapture(), lambda: settings, save, emit, tmp_path / "plugins", tmp_path / "data",
                   base_url=cdn.url, key_hex=cdn.key_hex)
    h.emitted, h.saved = emitted, settings
    h.overlay_calls = []

    async def overlay(command):
        h.overlay_calls.append(command)

    h.overlay = overlay
    yield h
    await h.stop()


def test_kleinigkeiten():
    assert newer("1.2.10", "1.2.9") and not newer("1.2.9", "1.2.9") and newer("1.1", "1.0.9")
    assert safe_path("a/b.js") and not safe_path("../x") and not safe_path("a//b") and not safe_path("/a")
    assert valid_id("pet-souls") and not valid_id("Ping") and not valid_id("../x") and not valid_id("")


def test_falsche_signatur_wird_abgelehnt():
    key = Ed25519PrivateKey.generate()
    key_hex = key.public_key().public_bytes(Encoding.Raw, PublicFormat.Raw).hex()
    body = b'{"format":1,"plugins":[]}'
    assert verify_catalog(body, key.sign(body).hex(), key_hex)["format"] == 1
    with pytest.raises(PluginError):
        verify_catalog(b'{"format":1,"plugins":[{}]}', key.sign(body).hex(), key_hex)
    with pytest.raises(PluginError):
        verify_catalog(body, "zz", key_hex)
    with pytest.raises(PluginError):
        verify_catalog(body, key.sign(body).hex(), Ed25519PrivateKey.generate().public_key().public_bytes(Encoding.Raw, PublicFormat.Raw).hex())


async def test_installieren_prueft_und_oeffnet(host, cdn):
    cdn.add("ping")
    view = await host.call("plugin_install", {"id": "ping"}, None)
    assert [p["id"] for p in view["plugins"]] == ["ping"] and view["online"] is True
    assert view["plugins"][0]["error"] is None and view["ownWindow"] == ["ping"]
    assert host.overlay_calls[-1]["action"] == "open" and host.overlay_calls[-1]["shown"] is True
    assert host.overlay_calls[-1]["width"] == 320 and host.overlay_calls[-1]["height"] == 430
    items = await host.call("plugin_catalog", {}, None)
    assert items[0]["installed"] == "1.0.0"
    assert host.windows_to_restore()[0]["shown"] is True


async def test_grosse_datei_kommt_ganz_an(host, cdn):
    cdn.add("ping", extra={"gross.bin": b"x" * (3 * 1024 * 1024)})
    await host.install("ping")
    assert (host.folder / "ping" / "gross.bin").stat().st_size == 3 * 1024 * 1024


async def test_zu_grosser_katalog_wird_abgelehnt(host, cdn):
    cdn.body = b" " * (1024 * 1024 + 1)
    with pytest.raises(PluginError, match="größer als"):
        await host.fetch_catalog()


async def test_veraenderte_datei_wird_nicht_installiert(host, cdn):
    cdn.add("ping")
    cdn.files["/ping/1.0.0/index.html"] = b"<script>boese</script>"
    with pytest.raises(PluginError, match="passt nicht zum Katalog"):
        await host.install("ping")
    assert "ping" not in host.loaded and not (host.folder / "ping").exists()


async def test_manifest_darf_nicht_mehr_als_der_katalog(host, cdn):
    cdn.add("ping", permissions=["storage"], manifest_permissions=["storage", "screenshot"])
    with pytest.raises(PluginError, match="Manifest passt nicht"):
        await host.install("ping")
    assert "ping" not in host.loaded


async def test_unsicherer_pfad_und_neuere_api(host, cdn):
    cdn.add("ping", extra={"ok.js": b"1"})
    entry = cdn.entries[0]
    entry["files"]["../raus.js"] = entry["files"].pop("ok.js")
    cdn.sign()
    with pytest.raises(PluginError, match="nicht erlaubt"):
        await host.install("ping")
    cdn.add("neu")
    cdn.entries[-1]["apiVersion"] = 3
    cdn.sign()
    with pytest.raises(PluginError, match="neueres NexBoard"):
        await host.install("neu")


async def test_kein_zurueck_auf_alten_katalog_oder_alte_version(host, cdn):
    cdn.add("ping", "2.0.0")
    await host.install("ping")
    cdn.serial = 50
    cdn.add("ping", "1.0.0")
    with pytest.raises(PluginError, match="älter"):
        await host.fetch_catalog()
    cdn.serial = 200
    cdn.add("ping", "1.0.0")
    with pytest.raises(PluginError, match="neuer als der Katalog"):
        await host.install("ping")
    assert host.loaded["ping"].manifest["version"] == "2.0.0"


async def test_geaenderter_ordner_laeuft_nicht(host, cdn):
    cdn.add("ping")
    await host.install("ping")
    (host.folder / "ping" / "index.html").write_text("<script>boese</script>")
    host.reload()
    assert "ping" not in host.loaded and "weicht" in host.errors["ping"]["error"]
    assert host.view()["plugins"][0]["error"]
    cdn.add("ping", "1.0.1")
    await host.install("ping")  # lässt sich aus dem Katalog reparieren
    assert "ping" in host.loaded and not host.errors


async def test_fremde_datei_im_ordner_laeuft_nicht(host, cdn):
    cdn.add("ping")
    await host.install("ping")
    (host.folder / "ping" / "extra.js").write_text("1")
    host.reload()
    assert "gehört nicht dazu" in host.errors["ping"]["error"]


async def test_entfernen_behaelt_daten(host, cdn):
    cdn.add("ping")
    await host.install("ping")
    await host.call("plugin_storage_set", {"key": "a", "value": "1"}, "plugin-ping")
    view = await host.call("plugin_uninstall", {"id": "ping"}, None)
    assert view["plugins"] == [] and host.overlay_calls[-1] == {"action": "close", "id": "ping"}
    assert (host.data_folder / "ping" / "a.json").read_text() == "1"
    cdn.add("ping", "1.0.1")
    await host.install("ping")
    assert await host.call("plugin_storage_get", {"key": "a"}, "plugin-ping") == "1"


async def test_update_prueft_neue_berechtigungen(host, cdn):
    cdn.add("ping")
    await host.install("ping")
    cdn.add("ping", "1.1.0", permissions=["storage", "fps"])
    cdn.entries[0]["changes"] = [{"version": "1.1.0", "en": "neu"}, {"version": "1.0.0", "en": "alt"}]
    cdn.sign()
    out = await host.check_updates()
    assert out["catalogError"] is None
    assert out["available"][0]["newPermissions"] == ["fps"] and out["available"][0]["to"] == "1.1.0"
    assert [c["version"] for c in out["available"][0]["changes"]] == ["1.1.0"]


async def test_berechtigungen_und_fensterkennung(host, cdn):
    cdn.add("ping", permissions=["storage"])
    await host.install("ping")
    with pytest.raises(PluginError, match="Berechtigung widgets"):
        await host.call("plugin_widget_open", {"name": "x"}, "plugin-ping")
    with pytest.raises(PluginError, match="Berechtigung feed"):
        await host.call("plugin_boss_timers", {"server": 2001}, "plugin-ping")
    with pytest.raises(PluginError, match="für Plugins nicht erlaubt"):
        await host.call("plugin_install", {"id": "ping"}, "plugin-ping")  # Plugins installieren keine Plugins
    with pytest.raises(PluginError, match="für Plugins nicht erlaubt"):
        await host.call("plugin_uninstall", {"id": "ping"}, "widget:ping:x")
    with pytest.raises(PluginError, match="kein Plugin-Fenster"):
        await host.call("plugin_hello", {}, None)
    with pytest.raises(PluginError, match="nicht geladen"):
        await host.call("plugin_hello", {}, "plugin-anderes")
    with pytest.raises(PluginError, match="Speicher-Schlüssel"):
        await host.call("plugin_storage_get", {"key": "../../x"}, "plugin-ping")
    with pytest.raises(PluginError, match="1 MB"):
        await host.call("plugin_storage_set", {"key": "a", "value": "x" * (1024 * 1024 + 1)}, "plugin-ping")


async def test_decoder_ereignisse_warten_und_kommen_einmal(host, cdn):
    cdn.add("seelen", permissions=["storage", "events:character", "decoder:s"],
            decoders=[{"name": "s", "opcode": "0D 90", "fields": []}])
    cdn.add("ohne", permissions=["storage"])
    await host.install("seelen")
    await host.install("ohne")
    host.character = {"name": "Navo"}
    await host._on_capture("plugin_frame", {"plugin": "seelen", "event": "decoded:s", "data": {"n": 1}, "immediate": False, "at": 5})
    now = host.pending[0].at
    assert take_ready(host.pending, now) == []  # wartet auf den Charakter
    ready = take_ready(host.pending, now + 1)
    await host.flush(ready)
    event, batch = host.emitted[-1]
    assert event == "plugin-events" and batch[0]["plugin"] == "seelen" and batch[0]["character"] == {"name": "Navo"}
    assert batch[0]["seq"] > 1_000_000_000  # zählt über Neustarts weiter, offene Seiten filtern danach
    hello = await host.call("plugin_hello", {"fresh": True}, "plugin-seelen")
    assert hello["replay"][0]["data"] == {"n": 1} and hello["character"] == {"name": "Navo"}
    assert "decoders" not in hello["manifest"]
    other = await host.call("plugin_hello", {}, "plugin-ohne")
    assert other["replay"] == [] and other["character"] is None  # ohne Berechtigung kein Charakter


def test_nichts_ueberholt_wartende():
    p = [Pending(0, True, 0, "a", "x", 1), Pending(0, False, 0, "a", "y", 2), Pending(0, False, 0, "b", "z", 3)]
    ready = take_ready(p, 0.1)
    assert [e.data for e in ready] == [3] and [e.data for e in p] == [1, 2]
    assert [e.data for e in take_ready(p, 9)] == [1, 2]


async def test_ereignisse_nur_mit_berechtigung(host, cdn):
    cdn.add("beute", permissions=["storage", "events:loot-rolls"])
    cdn.add("ping", permissions=["storage"])
    await host.install("beute")
    await host.install("ping")
    await host._on_capture("plugin_feed", {"event": "lootRoll", "data": {"id": "1"}, "at": 7})
    assert [p.plugin for p in host.pending] == ["beute"]
    host.pending.clear()
    host.emitted.clear()
    await host._on_capture("plugin_character", {"data": {"name": "Navo"}})
    assert host.emitted == []  # keins der beiden darf den Charakter sehen
    await host._on_capture("ping", 42)
    assert {e[1]["plugin"] for e in host.emitted} == {"beute", "ping"}


async def test_schwarzmarkt_und_kda_nur_mit_ihrem_recht(host, cdn):
    cdn.add("markt", permissions=["storage", "events:black-market"])
    cdn.add("pvp", permissions=["storage", "events:kda"])
    await host.install("markt")
    await host.install("pvp")
    await host._on_capture("plugin_feed", {"event": "blackMarket", "data": {"tab": 1}, "at": 7})
    await host._on_capture("plugin_feed", {"event": "kda", "data": {"kind": "kill"}, "at": 8})
    assert [(p.plugin, p.event) for p in host.pending] == [("markt", "blackMarket"), ("pvp", "kda")]


async def test_ausgeschaltet_bekommt_nichts(host, cdn):
    cdn.add("seelen", permissions=["storage", "decoder:s"], decoders=[{"name": "s", "opcode": "0D 90", "fields": []}])
    await host.install("seelen")
    host.capture.running = True
    view = await host.call("plugin_set_enabled", {"id": "seelen", "enabled": False}, None)
    assert view["disabled"] == ["seelen"] and host.overlay_calls[-1]["action"] == "close"
    assert host.capture.sent[-1] == ("plugin_decoders", {"plugins": []})
    await host._on_capture("plugin_frame", {"plugin": "seelen", "event": "decoded:s", "data": {}, "at": 1})
    assert host.pending == [] and host.windows_to_restore() == []
    await host.call("plugin_set_enabled", {"id": "seelen", "enabled": True}, None)
    assert host.capture.sent[-1][1]["plugins"][0]["plugin"] == "seelen"


async def test_widgets(host, cdn):
    cdn.add("ping", permissions=["storage", "widgets", "window"])
    await host.install("ping")
    host.screen = {"width": 1000, "height": 800}
    await host.call("plugin_widget_open", {"name": "a", "width": 100, "height": 50}, "plugin-ping")
    await host.call("plugin_widget_open", {"name": "b", "width": 5000, "height": 1}, "plugin-ping")
    state = host.widgets_state()
    assert state[0]["label"] == "widget:ping:a" and state[0]["x"] == 860  # freier Platz rechts
    assert state[1]["width"] == 800 and state[1]["height"] == 24  # Grenzen wie im Original
    with pytest.raises(PluginError, match="Widget-Name"):
        await host.call("plugin_widget_open", {"name": "../x"}, "plugin-ping")
    # Ziehen merkt sich den Platz und sagt es dem Plugin, außerhalb des Schirms geht nicht
    await host.call("plugin_widget_moved", {"label": "widget:ping:a", "x": 5000, "y": 10}, None)
    assert host.saved["dpsMeter.pluginWidget.ping.a"] == "900,10"
    assert any(e[0] == "plugin-event" and e[1].get("event") == "widget-moved" for e in host.emitted)
    # Nachricht nur an das eine Widget
    await host.call("plugin_widget_send", {"name": "a", "data": {"v": 1}}, "plugin-ping")
    sent = [e[1] for e in host.emitted if e[0] == "plugin-event" and e[1].get("event") == "widget"][-1]
    assert sent["__window"] == "widget:ping:a"
    # Widget an sein Plugin
    await host.call("plugin_widget_post", {"data": 7}, "widget:ping:a")
    posted = [e[1] for e in host.emitted if e[0] == "plugin-event" and e[1].get("event") == "widget-message"][-1]
    assert posted["data"] == {"name": "a", "data": 7}
    hello = await host.call("plugin_widget_hello", {}, "widget:ping:a")
    assert hello["name"] == "a" and hello["locked"] is False
    await host.call("plugin_widgets_lock", {"locked": True}, "plugin-ping")
    assert host.widgets_state()[0]["locked"] is True
    await host.call("plugin_widget_area", {"rects": [{"x": 1, "y": 2, "width": 3, "height": 4}], "scale": 1}, "widget:ping:a")
    assert host.widgets_state()[0]["areas"] == [[1.0, 2.0, 3.0, 4.0]]
    where = await host.call("plugin_widget_where", {"name": "a"}, "plugin-ping")
    assert where["x"] == 900 and where["screen"]["width"] == 1000
    await host.call("plugin_widget_close", {"name": "a"}, "plugin-ping")
    assert host.widgets_state()[0]["open"] is False
    await host.call("plugin_hello", {"fresh": True}, "plugin-ping")  # frischer Start: alte Widgets weg
    assert host.widgets_state() == []


async def test_fenster_merkt_sichtbarkeit(host, cdn):
    cdn.add("ping", permissions=["storage", "window"])
    await host.install("ping")
    await host.call("plugin_window", {"visible": False}, "plugin-ping")
    assert host.overlay_calls[-1] == {"action": "hide", "id": "ping"}
    assert host.windows_to_restore()[0]["shown"] is False
    await host.call("plugin_open", {"id": "ping"}, None)
    assert host.overlay_calls[-1]["shown"] is True and host.windows_to_restore()[0]["shown"] is True
    await host.call("plugin_window_fit", {"height": 10}, "plugin-ping")
    assert host.overlay_calls[-1] == {"action": "fit", "id": "ping", "height": 60.0}


async def test_fps_gibt_es_unter_linux_nicht(host, cdn):
    cdn.add("ping", permissions=["storage", "fps"])
    await host.install("ping")
    assert (await host.call("plugin_fps_watch", {"on": True}, "plugin-ping"))["state"] == "unsupported"


async def test_farbschema_nur_gueltige_farben(host):
    with pytest.raises(PluginError):
        await host.call("set_plugin_theme", {"theme": {"bg": "red;}", "panel": "#000000", "accent": "#000000"}}, None)
    await host.call("set_plugin_theme", {"theme": {"bg": "#111111", "panel": "#222222", "accent": "#333333", "x": 1}}, None)
    assert host.theme() == {"bg": "#111111", "panel": "#222222", "accent": "#333333"}


def test_csp_ohne_netz():
    policy = content_policy("http://127.0.0.1:8766", "/__a2plugin__/", "ping")
    assert "connect-src 'none'" in policy and "default-src 'none'" in policy and "frame-src 'none'" in policy
    assert "http://127.0.0.1:8766/__a2plugin__/ping/" in policy
    assert "__a2plugin__/../" not in content_policy("http://x", "/__a2plugin__/", "../")


# ---------------------------------------------------------------- HTTP (a2ui.py)
@pytest.fixture
async def ui(tmp_path, cdn):
    a2 = A2Ui(FakeCapture(), tmp_path / "s.json", plugin_dir=tmp_path)
    a2.plugins.base_url, a2.plugins.key_hex = cdn.url, cdn.key_hex
    client = TestClient(TestServer(a2.app()))
    await client.start_server()
    a2.client = client
    yield a2
    await client.close()
    await a2.plugins.stop()


async def test_plugin_dateien_mit_csp(ui, cdn):
    cdn.add("ping", extra={"sub/a.js": b"1"})
    await ui.plugins.install("ping")
    r = await ui.client.get("/__a2plugin__/ping/index.html")
    text = await r.text()
    assert r.status == 200 and "connect-src 'none'" in r.headers["Content-Security-Policy"]
    assert "@font-face" in text and text.index("<head>") < text.index("@font-face")
    r = await ui.client.get("/__a2plugin__/ping/sub/a.js")
    assert r.status == 200 and await r.read() == b"1"
    r = await ui.client.get("/_sdk/a2.js")
    assert r.status == 200 and "window.a2" in await r.text()
    assert (await ui.client.get("/__a2plugin__/ping/%2e%2e/%2e%2e/s.json")).status == 404
    assert (await ui.client.get("/__a2plugin__/anderes/index.html")).status == 404


async def test_host_seiten_bekommen_das_shim(ui):
    for page in ("/plugin-host.html", "/plugin-widget.html"):
        text = await (await ui.client.get(page)).text()
        assert "/__deckbar__/a2shim.js" in text and text.index("a2shim") < text.index("<script src=\"/src/js/plugin")
    assert (await ui.client.get("/__deckbar__/a2events.js")).status == 200


async def test_invoke_leitet_an_den_host(ui, cdn):
    cdn.add("ping")
    r = await ui.client.post("/api/a2/invoke", json={"cmd": "plugin_catalog", "args": {}})
    assert (await r.json())["result"][0]["id"] == "ping"
    r = await ui.client.post("/api/a2/invoke", json={"cmd": "plugin_install", "args": {"id": "ping"}, "window": "plugin-ping"})
    assert r.status == 500 and "nicht erlaubt" in (await r.json())["error"]
    # Fensterkennung eines Plugins kommt nur an seine Befehle, auch bei Meter-Befehlen
    r = await ui.client.post("/api/a2/invoke", json={"cmd": "clear_settings", "args": {}, "window": "plugin-ping"})
    assert r.status == 500
    r = await ui.client.post("/api/a2/invoke", json={"cmd": "meter_shown", "args": {}})
    assert (await r.json())["result"] is True


# ---------------------------------------------------------------- Im Radar-Widget
async def test_pet_soul_und_wuerfel_laufen_im_radar(host, cdn):
    cdn.add("pet-souls", permissions=["storage", "window", "widgets"])
    cdn.add("dice-rolls", permissions=["storage", "window", "widgets"])
    cdn.add("ping", permissions=["storage", "window"])
    for plugin in ("pet-souls", "dice-rolls", "ping"):
        await host.install(plugin)
    assert [w["id"] for w in host.windows_to_restore()] == ["ping"]  # nur Ping bekommt ein Fenster
    assert host.embedded() == ["dice-rolls", "pet-souls"]
    assert not any(c.get("id") in ("pet-souls", "dice-rolls") for c in host.overlay_calls)
    assert ("plugin-embed", {"plugin": "pet-souls", "shown": False}) in host.emitted  # springt nicht nach vorn
    assert ("plugin-embed", {"plugin": "dice-rolls", "shown": True}) in host.emitted
    assert (await host.call("plugin_hello", {}, "plugin-pet-souls"))["visible"] is True
    host.emitted.clear()
    # Pet Soul holt sich nicht nach vorn, ein Klick auf die Würfelkarte schon
    await host.call("plugin_window", {"visible": True}, "plugin-pet-souls")
    assert host.emitted == []
    await host.call("plugin_window", {"visible": True}, "plugin-dice-rolls")
    assert host.emitted == [("plugin-embed", {"plugin": "dice-rolls", "shown": True})]
    await host.call("plugin_close", {}, "plugin-pet-souls")
    await host.call("plugin_window_fit", {"height": 80}, "plugin-pet-souls")
    assert not any(c.get("id") == "pet-souls" for c in host.overlay_calls)


async def test_pet_soul_karte_steht_fest_auf_ausgelagert(host, cdn):
    cdn.add("pet-souls", permissions=["storage"])
    await host.install("pet-souls")
    prefs = json.loads(await host.call("plugin_storage_get", {"key": "prefs"}, "plugin-pet-souls"))
    assert prefs == {"nearby": True, "mapPopped": True, "farmPopup": False}
    await host.call("plugin_storage_set", {"key": "prefs", "value": json.dumps({"sort": "left", "nearby": False})}, "plugin-pet-souls")
    prefs = json.loads(await host.call("plugin_storage_get", {"key": "prefs"}, "plugin-pet-souls"))
    assert prefs["sort"] == "left" and prefs["nearby"] is True
    assert await host.call("plugin_storage_get", {"key": "anderes"}, "plugin-pet-souls") is None


async def test_pet_art_filter_geht_an_die_radar_karte(host, cdn):
    cdn.add("pet-souls", permissions=["storage"])
    await host.install("pet-souls")
    host.emitted.clear()
    await host.call("plugin_storage_set", {"key": "prefs", "value": json.dumps({"genus": "fera"})}, "plugin-pet-souls")
    await host.call("plugin_storage_set", {"key": "prefs", "value": json.dumps({"genus": ""})}, "plugin-pet-souls")
    await host.call("plugin_storage_set", {"key": "andere", "value": json.dumps({"genus": "fera"})}, "plugin-pet-souls")
    assert host.emitted == [("radar-pet-art", {"art": "fera"}), ("radar-pet-art", {"art": ""})]


# ---------------------------------------------------------------- Fest eingebaut
async def test_pet_soul_installiert_und_aktualisiert_sich_selbst(host, cdn):
    cdn.add("pet-souls", "1.0.0", permissions=["storage"])
    await host._install_builtin()
    assert host.loaded["pet-souls"].manifest["version"] == "1.0.0" and host.embedded() == ["pet-souls"]
    cdn.add("pet-souls", "1.1.0", permissions=["storage"])
    await host._install_builtin()
    assert host.loaded["pet-souls"].manifest["version"] == "1.1.0"
    # Will es mehr dürfen: bleibt auf der alten Version und erscheint zur Zustimmung im Meter
    cdn.add("pet-souls", "2.0.0", permissions=["storage", "screenshot"])
    await host._install_builtin()
    assert host.loaded["pet-souls"].manifest["version"] == "1.1.0"
    assert [p["id"] for p in host.view()["plugins"]] == ["pet-souls"]
    waiting = (await host.check_updates())["available"]
    assert [(a["id"], a["newPermissions"]) for a in waiting] == [("pet-souls", ["screenshot"])]
    await host.install("pet-souls")  # Zustimmung im Dialog
    assert host.loaded["pet-souls"].manifest["version"] == "2.0.0" and host.view()["plugins"] == []


async def test_pet_soul_steht_in_keiner_liste_und_bleibt_an(host, cdn):
    cdn.add("pet-souls", permissions=["storage"])
    cdn.add("ping", permissions=["storage"])
    await host._install_builtin()
    await host.install("ping")
    view = await host.call("plugin_list", {}, None)
    assert [p["id"] for p in view["plugins"]] == ["ping"] and "pet-souls" not in view["ownWindow"]
    assert [e["id"] for e in await host.call("plugin_catalog", {}, None)] == ["ping"]
    with pytest.raises(PluginError, match="ausschalten"):
        await host.call("plugin_set_enabled", {"id": "pet-souls", "enabled": False}, None)
    with pytest.raises(PluginError, match="entfernen"):
        await host.call("plugin_uninstall", {"id": "pet-souls"}, None)
    # früher ausgeschaltet oder geänderter Ordner: läuft wieder, wird neu geholt
    host.saved["dpsMeter.pluginsDisabled"] = '["pet-souls"]'
    assert "pet-souls" in host.embedded()
    (host.folder / "pet-souls" / "index.html").write_text("boese")
    host.reload()
    assert "pet-souls" not in host.loaded and (await host.call("plugin_list", {}, None))["plugins"][0]["id"] == "ping"
    await host._install_builtin()
    assert "pet-souls" in host.loaded and not host.errors


async def test_ohne_netz_wird_es_spaeter_versucht(host, cdn, monkeypatch):
    import deckbar_daemon.plugins as modul
    monkeypatch.setattr(modul, "BUILTIN_RETRY", 0.01)
    cdn.add("pet-souls", permissions=["storage"])
    gut = cdn.signature
    cdn.signature = b"00"
    task = asyncio.create_task(host._keep_builtin())
    await asyncio.sleep(0.05)
    assert "pet-souls" not in host.loaded and not task.done()
    cdn.signature = gut
    await asyncio.wait_for(task, 5)
    assert "pet-souls" in host.loaded
