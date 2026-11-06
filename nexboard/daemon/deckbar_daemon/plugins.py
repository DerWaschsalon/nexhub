"""A2Tools-Plugins im NexBoard, ohne das Meter-Programm.

Nachbau des Plugin-Hosts aus capture/a2tools/src-tauri/src/plugins (dort an Tauri-Fenster gebunden),
gleiches Verhalten und gleiche Grenzen. Die Seiten kommen unverändert aus dem Submodul
(plugin-host.html, plugin-widget.html, pluginSettings.js), sie sprechen über web/a2shim.js mit `call`.

    Katalog      signierter Katalog von cdn.a2tools.app, Ed25519, Dateien gegen ihre SHA-256 geprüft.
                 Eine Installation behält den signierten Katalog (.proof) und wird bei jedem Laden
                 dagegen geprüft; ein geänderter Plugin-Ordner läuft nicht.
    Daten        deckbar-capture liefert Decoder-Ereignisse und Spielstand (capture/src/plugins.rs).
                 Der Stand aus dem Mitschnitt geht nur an Plugins mit passender Berechtigung.
    Fenster      das Hauptfenster eines Plugins macht das Overlay-Programm (Befehle `plugin …` über
                 dessen Socket), Widgets die Overlay-Seite (web/overlay/plugins.js).

Plugin-Seiten laufen in einem Sandbox-iframe mit eigener, leerer Herkunft und CSP ohne Netz. Sie erreichen
den Daemon nicht direkt (local_only lehnt ihren Origin ab); was sie dürfen, prüfen pluginFrame.js und `require`.
"""
from __future__ import annotations

import asyncio
import base64
import hashlib
import json
import logging
import os
import re
import shutil
import time
from collections import deque
from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import aiohttp
from cryptography.exceptions import InvalidSignature
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PublicKey

log = logging.getLogger(__name__)

BASE_URL = "https://cdn.a2tools.app/plugins"
FEED_URL = "https://cdn.a2tools.app/feeds"
LIVE_URL = "wss://a2tools.app/api/boss-timers/live"
# Öffentlicher Schlüssel des Katalogs (src-tauri/src/plugins/catalog.rs, PUBLIC_KEY_HEX)
PUBLIC_KEY_HEX = "d71e888cd5530b57254a4f87bf8f1861d8ddd8f7ddf45ecdba0771bb8f7d54ae"
API_VERSION = 2
PROOF_DIR = ".proof"
MAX_CATALOG = 1024 * 1024
MAX_PLUGIN = 8 * 1024 * 1024
PARALLEL_DOWNLOADS = 4
CATALOG_MAX_AGE = 300.0

MAX_STORED = 1024 * 1024
MAX_STORED_KEYS = 256
MAX_WIDGETS = 16
MAX_MESSAGE = 64 * 1024
MAX_AREAS = 64
MAX_FOLLOW = 50
MIN_PANEL_HEIGHT = 60.0
SETTLE = 0.5  # Decoder-Ereignisse warten auf den Charakter (beim Login kommt er erst danach)
BATCH_WAIT = 0.04
MAX_LOGGED = 20_000
MAX_LOGGED_BYTES = 2 * 1024 * 1024
GAME_CHECK = 5.0
FEED_CACHE = 2.0

WINDOWS_KEY = "dpsMeter.pluginWindows"
DISABLED_KEY = "dpsMeter.pluginsDisabled"
HIDE_CLOSED_KEY = "dpsMeter.pluginsHideClosed"
HIDE_UNFOCUSED_KEY = "dpsMeter.pluginsHideUnfocused"
THEME_KEY = "dpsMeter.pluginTheme"
DEFAULT_THEME = {"bg": "#0a0e16", "panel": "#0a0e16", "accent": "#8fc2ff"}
LANGUAGE_KEY = "dpsMeter.language"
HEX_COLOR = re.compile(r"#[0-9a-fA-F]{6}")
STORAGE_KEY = re.compile(r"[A-Za-z0-9_-]{1,64}")
WIDGET_NAME = re.compile(r"[a-z0-9-]{1,32}")
PLAIN_NAME = re.compile(r"[A-Za-z0-9._-]+")

# Laufen im Radar-Widget der Overlay-Seite (web/overlay/radar.js), nicht im eigenen Fenster. Der Pet Soul
# Tracker schickt seine Karte als Szene an ein Widget, das Radar zeichnet sie auf seiner Karte: dafür steht
# die Karte fest auf „ausgelagert“. Sein Aufklappen beim Farmen wäre im Radar ein Reiterwechsel.
EMBEDDED = {"pet-souls", "dice-rolls"}
EMBEDDED_PREFS = {"pet-souls": {"nearby": True, "mapPopped": True, "farmPopup": False}}
# Was eine Plugin-Seite (Fenster oder Widget) aufrufen darf, wie PLUGIN_SURFACE_COMMANDS im Original
SURFACE = {
    "meter_shown", "set_meter_shown", "open_settings_at", "open_settings_window", "open_url",
    "plugin_abyss_siege", "plugin_boss_follow", "plugin_boss_timers", "plugin_close", "plugin_fps_admin",
    "plugin_fps_watch", "plugin_hello", "plugin_screenshot", "plugin_set_docked", "plugin_storage_get",
    "plugin_storage_set", "plugin_widget_area", "plugin_widget_close", "plugin_widget_drag",
    "plugin_widget_hello", "plugin_widget_open", "plugin_widget_place", "plugin_widget_post",
    "plugin_widget_send", "plugin_widget_where", "plugin_widgets_lock", "plugin_widgets_locked",
    "plugin_window", "plugin_window_fit", "start_tool_drag", "window_resize_drag", "get_settings",
}


class PluginError(RuntimeError):
    """Fehlertext für die Oberfläche."""


def valid_id(plugin: str) -> bool:
    return 0 < len(plugin) <= 40 and all(c.islower() and c.isascii() or c.isdigit() and c.isascii() or c == "-" for c in plugin)


def safe_path(path: str) -> bool:
    return 0 < len(path) <= 128 and all(
        p not in ("", ".", "..") and PLAIN_NAME.fullmatch(p) for p in path.split("/"))


def newer(candidate: str, current: str) -> bool:
    """Ob `candidate` eine spätere Version ist ("1.2.10" > "1.2.9")."""
    def parts(v: str) -> list[int]:
        return [int(p) if p.isdigit() else 0 for p in v.split(".")]
    a, b = parts(candidate), parts(current)
    n = max(len(a), len(b))
    return a + [0] * (n - len(a)) > b + [0] * (n - len(b))


def sha256_hex(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def verify_catalog(body: bytes, signature_hex: str, key_hex: str = PUBLIC_KEY_HEX) -> dict:
    """Signatur prüfen und den Katalog lesen."""
    try:
        key = Ed25519PublicKey.from_public_bytes(bytes.fromhex(key_hex))
        key.verify(bytes.fromhex(signature_hex.strip()), body)
    except (ValueError, InvalidSignature) as e:
        raise PluginError("Die Signatur des Plugin-Katalogs stimmt nicht: keine Installation daraus") from e
    catalog = json.loads(body)
    if catalog.get("format") != 1:
        raise PluginError(f"Plugin-Katalog im Format {catalog.get('format')}: dieses NexBoard liest Format 1")
    return catalog


def load_manifest(folder: Path) -> dict:
    """Manifest eines Plugin-Ordners lesen und prüfen."""
    try:
        manifest = json.loads((folder / "manifest.json").read_text(encoding="utf-8"))
    except (OSError, ValueError) as e:
        raise PluginError(f"manifest.json: {e}") from e
    if not isinstance(manifest, dict) or not valid_id(str(manifest.get("id", ""))):
        raise PluginError("manifest.json: Kennung ungültig")
    api = manifest.get("apiVersion")
    if not isinstance(api, int) or not 0 < api <= API_VERSION:
        raise PluginError(f"apiVersion {api} (dieses NexBoard kann bis {API_VERSION}): NexBoard aktualisieren")
    if not (folder / "index.html").is_file():
        raise PluginError("index.html fehlt")
    permissions = manifest.get("permissions") or []
    for spec in manifest.get("decoders") or []:
        if f"decoder:{spec.get('name')}" not in permissions:
            raise PluginError(f"Decoder {spec.get('name')} braucht die Berechtigung decoder:{spec.get('name')}")
    return manifest


def check_files(entry: dict, folder: Path) -> None:
    """Der Ordner enthält genau die Dateien des Katalogs."""
    files: dict[str, str] = entry.get("files") or {}
    found = set()
    total = 0
    root = folder.resolve()
    for path in sorted(folder.rglob("*")):
        if path.is_symlink():
            raise PluginError(f"{path.name} ist ein Link")
        if path.is_dir():
            continue
        rel = path.relative_to(folder).as_posix()
        want = files.get(rel)
        if want is None or not path.resolve().is_relative_to(root):
            raise PluginError(f"{rel} gehört nicht dazu")
        data = path.read_bytes()
        total += len(data)
        if total > MAX_PLUGIN:
            raise PluginError(f"größer als {MAX_PLUGIN} Byte")
        if sha256_hex(data).lower() != want.lower():
            raise PluginError(f"{rel} weicht vom Katalog ab")
        found.add(rel)
    missing = set(files) - found
    if missing:
        raise PluginError(f"{sorted(missing)[0]} fehlt")


@dataclass
class Loaded:
    manifest: dict
    folder: Path

    @property
    def id(self) -> str:
        return self.manifest["id"]

    @property
    def permissions(self) -> list[str]:
        return self.manifest.get("permissions") or []

    def public(self) -> dict:
        m = self.manifest
        return {"id": m["id"], "name": m.get("name", m["id"]), "version": m.get("version", ""),
                "apiVersion": m.get("apiVersion"), "description": m.get("description", ""),
                "author": m.get("author", ""), "permissions": self.permissions, "ui": m.get("ui")}


@dataclass
class Pending:
    at: float
    settle: bool
    read_ms: int
    plugin: str
    event: str
    data: Any


@dataclass
class EventLog:
    events: deque = field(default_factory=deque)
    size: int = 0


@dataclass
class WidgetState:
    plugin: str
    name: str
    width: float
    height: float
    x: int = 0
    y: int = 0
    open: bool = True
    areas: list[list[float]] | None = None

    @property
    def label(self) -> str:
        return f"widget:{self.plugin}:{self.name}"


def take_ready(pending: list[Pending], now: float) -> list[Pending]:
    """Was jetzt raus darf, in Reihenfolge: nichts überholt ein wartendes Ereignis seines Plugins."""
    held: set[str] = set()
    ready: list[Pending] = []
    waiting: list[Pending] = []
    for p in pending:
        if (not p.settle or now - p.at >= SETTLE) and p.plugin not in held:
            ready.append(p)
        else:
            held.add(p.plugin)
            waiting.append(p)
    pending[:] = waiting
    return ready


class PluginHost:
    def __init__(self, capture: Any, settings: Callable[[], dict[str, str]], save_setting: Callable[[str, str], None],
                 emit: Callable[[str, Any], Awaitable[None]], folder: Path, data_folder: Path,
                 base_url: str = BASE_URL, key_hex: str = PUBLIC_KEY_HEX) -> None:
        self.capture = capture
        self.settings = settings
        self.save_setting = save_setting
        self.emit = emit
        self.folder = folder
        self.data_folder = data_folder
        self.base_url = base_url
        self.key_hex = key_hex
        self.overlay: Callable[[dict], Awaitable[None]] | None = None  # Befehle ans Overlay-Programm
        self.loaded: dict[str, Loaded] = {}
        self.errors: dict[str, dict] = {}
        self.decoder_errors: dict[str, str] = {}
        self.widgets: dict[str, WidgetState] = {}
        self.pending: list[Pending] = []
        self.logs: dict[str, EventLog] = {}
        self.run = str(int(time.time() * 1000))
        # Zählt über Neustarts hinweg weiter: offene Seiten merken sich die letzte Nummer
        self.seq = int(time.time() * 1000)
        self.character: Any = None
        self.screen = {"width": 1920, "height": 1080}
        self.game = False
        self._catalog: tuple[float, dict, str, str] | None = None
        self._feeds: dict[tuple[str, int], tuple[float, Any]] = {}
        self._follows: dict[tuple[str, int], set[str]] = {}
        self._live: dict[int, asyncio.Task] = {}
        self._live_wanted: dict[int, asyncio.Event] = {}
        self._http: aiohttp.ClientSession | None = None
        self._wake = asyncio.Event()
        self._tasks: list[asyncio.Task] = []
        capture.data_listeners.append(self._on_capture)
        self.reload()

    # ------------------------------------------------------------ Einstellungen
    def _listed(self, key: str) -> list[str]:
        try:
            value = json.loads(self.settings().get(key) or "[]")
        except ValueError:
            return []
        return [str(v) for v in value] if isinstance(value, list) else []

    def _save_list(self, key: str, ids: list[str]) -> None:
        self.save_setting(key, json.dumps(ids))

    def disabled(self) -> list[str]:
        return self._listed(DISABLED_KEY)

    def _windows(self) -> dict[str, str]:
        try:
            value = json.loads(self.settings().get(WINDOWS_KEY) or "{}")
        except ValueError:
            return {}
        return {str(k): str(v) for k, v in value.items()} if isinstance(value, dict) else {}

    def _remember_window(self, plugin: str, state: str | None) -> None:
        windows = self._windows()
        if state is None:
            windows.pop(plugin, None)
        else:
            windows[plugin] = state
        self.save_setting(WINDOWS_KEY, json.dumps(windows))

    def language(self) -> str:
        return self.settings().get(LANGUAGE_KEY) or "en"

    def theme(self) -> dict:
        try:
            return clean_theme(json.loads(self.settings().get(THEME_KEY) or "null")) or DEFAULT_THEME
        except ValueError:
            return DEFAULT_THEME

    # ------------------------------------------------------------ Laden
    def _proof(self, plugin: str) -> Path:
        return self.folder / PROOF_DIR / f"{plugin}.json"

    def _verify_installed(self, plugin: str, folder: Path, version: str) -> None:
        try:
            signed = json.loads(self._proof(plugin).read_text())
            index, signature = signed["index"], signed["signature"]
        except (OSError, ValueError, KeyError, TypeError) as e:
            raise PluginError("ohne Nachweis aus dem Katalog: bitte neu installieren") from e
        catalog = verify_catalog(index.encode(), signature, self.key_hex)
        entry = next((e for e in catalog.get("plugins", []) if e.get("id") == plugin and e.get("version") == version), None)
        if entry is None:
            raise PluginError(f"der Katalog kennt {plugin} {version} nicht")
        check_files(entry, folder)

    def reload(self) -> None:
        loaded: dict[str, Loaded] = {}
        errors: dict[str, dict] = {}
        try:
            folders = sorted(p for p in self.folder.iterdir() if p.is_dir() and not p.name.startswith("."))
        except OSError:
            folders = []
        for folder in folders:
            try:
                manifest = load_manifest(folder)
                if manifest["id"] != folder.name:
                    raise PluginError("Ordner und Kennung passen nicht zusammen")
                self._verify_installed(manifest["id"], folder, str(manifest.get("version", "")))
                loaded[manifest["id"]] = Loaded(manifest, folder)
            except PluginError as e:
                log.warning("Plugin %s läuft nicht: %s", folder.name, e)
                errors[folder.name] = {"id": folder.name, "name": folder.name, "version": "", "description": "",
                                       "path": str(folder), "permissions": [], "reviewed": True, "error": str(e)}
        self.loaded, self.errors = loaded, errors

    def info(self, p: Loaded) -> dict:
        m = p.manifest
        return {"id": p.id, "name": m.get("name", p.id), "version": m.get("version", ""),
                "description": m.get("description", ""), "path": str(p.folder), "permissions": p.permissions,
                "reviewed": True, "error": self.decoder_errors.get(p.id)}

    def view(self) -> dict:
        return {"devMode": False, "online": True,
                "plugins": [self.info(p) for p in self.loaded.values()] + list(self.errors.values()),
                "disabled": self.disabled(), "hideClosed": self._listed(HIDE_CLOSED_KEY),
                "hideUnfocused": self._listed(HIDE_UNFOCUSED_KEY),
                # Ein Dock wie im Meter gibt es nicht: jedes Plugin hat sein Fenster
                "ownWindow": list(self.loaded)}

    async def send_decoders(self) -> None:
        """Decoder der laufenden Plugins an deckbar-capture (auch nach dessen Neustart)."""
        if not self.capture.running:
            return
        off = set(self.disabled())
        plugins = [{"plugin": p.id, "decoders": p.manifest.get("decoders") or []}
                   for p in self.loaded.values() if p.id not in off]
        try:
            result = await self.capture.request("plugin_decoders", timeout=10, plugins=plugins)
        except (RuntimeError, TimeoutError) as e:
            log.warning("Plugin-Decoder nicht gesetzt: %s", e)
            return
        self.decoder_errors = {}
        for text in (result or {}).get("errors") or []:
            plugin, _, why = str(text).partition(": ")
            self.decoder_errors[plugin] = why
            log.warning("Plugin %s: Decoder abgelehnt: %s", plugin, why)

    def start(self) -> None:
        if not self._tasks:
            self._tasks = [asyncio.create_task(self._flusher()), asyncio.create_task(self._game_loop())]

    async def stop(self) -> None:
        for task in [*self._tasks, *self._live.values()]:
            task.cancel()
        await asyncio.gather(*self._tasks, *self._live.values(), return_exceptions=True)
        self._tasks, self._live = [], {}
        if self._http:
            await self._http.close()
            self._http = None

    # ------------------------------------------------------------ Ereignisse aus dem Mitschnitt
    async def _on_capture(self, event: str, payload: Any) -> None:
        if event == "hello":
            self.start()
            asyncio.ensure_future(self.send_decoders())
        elif event == "ping":
            await self.tell_all("ping", {"ms": payload})
        elif event == "plugin_character":
            self.character = payload.get("data")
            await self.tell_permitted("events:character", "character", self.character)
        elif event == "plugin_frame":
            await self._on_frame(payload)
        elif event == "plugin_feed":
            await self._on_feed(payload)

    def _on_ids(self, permission: str | None = None) -> list[str]:
        off = set(self.disabled())
        return [p.id for p in self.loaded.values()
                if p.id not in off and (permission is None or permission in p.permissions)]

    async def _on_frame(self, msg: dict) -> None:
        plugin = str(msg.get("plugin"))
        p = self.loaded.get(plugin)
        if p is None or plugin in self.disabled():
            return
        settle = not msg.get("immediate") and "events:character" in p.permissions
        self.pending.append(Pending(time.monotonic(), settle, int(msg.get("at") or 0), plugin,
                                    str(msg.get("event")), msg.get("data")))
        self._wake.set()

    async def _on_feed(self, msg: dict) -> None:
        event, data = str(msg.get("event")), msg.get("data")
        if event in ("bossMap", "abyss"):
            await self.tell_permitted("feed:boss-timers", event, data)
            return
        permission = {"deathRecap": "events:death-recap", "lootRoll": "events:loot-rolls"}.get(event)
        if permission:
            now = time.monotonic()
            self.pending.extend(Pending(now, False, int(msg.get("at") or 0), plugin, event, data)
                                for plugin in self._on_ids(permission))
            self._wake.set()

    async def _flusher(self) -> None:
        while True:
            await self._wake.wait()
            await asyncio.sleep(BATCH_WAIT)
            if not self.pending:
                self._wake.clear()
                continue
            await self.flush(take_ready(self.pending, time.monotonic()))

    async def flush(self, ready: list[Pending]) -> None:
        """Nummerieren, mit dem Charakter versehen, für später geöffnete Fenster behalten, schicken."""
        if not ready:
            return
        events = []
        for item in ready:
            p = self.loaded.get(item.plugin)
            self.seq += 1
            event = {"plugin": item.plugin, "seq": self.seq, "event": item.event, "data": item.data, "at": item.read_ms,
                     "character": self.character if p and "events:character" in p.permissions else None}
            self._keep(item.plugin, event)
            events.append(event)
        await self.emit("plugin-events", events)

    def _keep(self, plugin: str, event: dict) -> None:
        text = json.dumps(event, ensure_ascii=False)
        entry = self.logs.setdefault(plugin, EventLog())
        entry.events.append(text)
        entry.size += len(text)
        while entry.events and (len(entry.events) > MAX_LOGGED or entry.size > MAX_LOGGED_BYTES):
            entry.size -= len(entry.events.popleft())

    async def _game_loop(self) -> None:
        while True:
            running = bool(self.capture.status.get("game"))
            if running != self.game:
                self.game = running
                await self.tell_all("game", {"running": running})
            await asyncio.sleep(GAME_CHECK)

    async def tell_all(self, event: str, data: Any) -> None:
        for plugin in self._on_ids():
            await self.emit("plugin-event", {"plugin": plugin, "event": event, "data": data})

    async def tell_permitted(self, permission: str, event: str, data: Any) -> None:
        for plugin in self._on_ids(permission):
            await self.emit("plugin-event", {"plugin": plugin, "event": event, "data": data})

    # ------------------------------------------------------------ Katalog und Installation
    async def _session(self) -> aiohttp.ClientSession:
        if self._http is None or self._http.closed:
            self._http = aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=300))
        return self._http

    async def _get(self, url: str, cap: int) -> bytes:
        http = await self._session()
        async with http.get(url) as r:
            if r.status != 200:
                raise PluginError(f"{url}: HTTP {r.status}")
            data = bytearray()
            async for chunk in r.content.iter_chunked(64 * 1024):
                data += chunk
                if len(data) > cap:
                    raise PluginError(f"{url}: größer als {cap} Byte")
            return bytes(data)

    def _check_serial(self, serial: int) -> None:
        """Einen älteren Katalog als den schon gelesenen ablehnen (alter signierter Stand erneut ausgeliefert)."""
        path = self.folder / PROOF_DIR / "serials.json"
        try:
            seen = json.loads(path.read_text())
        except (OSError, ValueError):
            seen = {}
        last = int(seen.get("main", 0))
        if serial < last:
            raise PluginError(f"Der Plugin-Katalog ist älter als ein schon gelesener ({serial} < {last})")
        if serial > last:
            seen["main"] = serial
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(json.dumps(seen))

    async def fetch_catalog(self, max_age: float = 0) -> dict:
        now = time.monotonic()
        if self._catalog and now - self._catalog[0] < max_age:
            return self._catalog[1]
        body, signature = await asyncio.gather(self._get(f"{self.base_url}/index.json", MAX_CATALOG),
                                               self._get(f"{self.base_url}/index.json.sig", 1024))
        text = signature.decode("ascii", "replace").strip()
        catalog = verify_catalog(body, text, self.key_hex)
        self._check_serial(int(catalog.get("serial") or 0))
        self._catalog = (now, catalog, body.decode("utf-8"), text)
        return catalog

    async def catalog_items(self) -> list[dict]:
        catalog = await self.fetch_catalog(CATALOG_MAX_AGE)
        return [{"id": e.get("id"), "name": e.get("name"), "version": e.get("version"),
                 "description": e.get("description", ""), "author": e.get("author", ""),
                 "permissions": e.get("permissions") or [], "source": e.get("source", ""),
                 "installed": self.loaded[e["id"]].manifest.get("version") if e.get("id") in self.loaded else None,
                 "test": False, "changes": e.get("changes") or []} for e in catalog.get("plugins", [])]

    async def install(self, plugin: str) -> dict:
        plugin = plugin.strip().lower()
        catalog = await self.fetch_catalog()
        entry = next((e for e in catalog.get("plugins", []) if e.get("id") == plugin), None)
        if entry is None:
            raise PluginError("Dieses Plugin steht nicht im Katalog")
        files = await self._download(entry)
        await self.emit("plugin-install-phase", {"id": plugin, "phase": "installing"})
        updating = plugin in self.loaded
        await asyncio.to_thread(self._write_install, entry, files)
        self.reload()
        await self.send_decoders()
        if plugin in self.errors:
            raise PluginError(self.errors[plugin]["error"])
        log.info("Plugin %s %s installiert", plugin, entry.get("version"))
        if updating:
            await self._overlay({"action": "reload", "id": plugin})
        else:
            self._remember_window(plugin, "shown")
            await self._open(plugin, True)
        return self.view()

    async def _download(self, entry: dict) -> list[tuple[str, bytes]]:
        plugin = str(entry.get("id"))
        if not valid_id(plugin):
            raise PluginError(f"Plugin-Kennung {plugin!r} ungültig")
        api = entry.get("apiVersion")
        if not isinstance(api, int) or not 0 < api <= API_VERSION:
            raise PluginError(f"{entry.get('name')} braucht ein neueres NexBoard (Plugin-API {api})")
        files: dict[str, str] = entry.get("files") or {}
        if "manifest.json" not in files or "index.html" not in files:
            raise PluginError(f"{entry.get('name')}: Manifest oder Seite fehlt")
        for path in files:
            if not safe_path(path):
                raise PluginError(f"{entry.get('name')}: Datei {path!r} nicht erlaubt")
        limit = asyncio.Semaphore(PARALLEL_DOWNLOADS)

        async def one(path: str, want: str) -> tuple[str, bytes]:
            url = f"{self.base_url}/{plugin}/{entry.get('version')}/{path}"
            async with limit:
                try:
                    data = await self._get(url, MAX_PLUGIN)
                except (PluginError, aiohttp.ClientError, TimeoutError):
                    data = await self._get(url, MAX_PLUGIN)
            if sha256_hex(data).lower() != want.lower():
                raise PluginError(f"{entry.get('name')}: {path} passt nicht zum Katalog, keine Installation")
            return path, data

        try:
            got = await asyncio.gather(*(one(p, h) for p, h in files.items()))
        except (aiohttp.ClientError, TimeoutError) as e:
            raise PluginError(f"Download fehlgeschlagen: {e}") from e
        if sum(len(d) for _, d in got) > MAX_PLUGIN:
            raise PluginError(f"{entry.get('name')} ist größer als {MAX_PLUGIN} Byte")
        return got

    def _write_install(self, entry: dict, files: list[tuple[str, bytes]]) -> None:
        assert self._catalog
        plugin = entry["id"]
        self.folder.mkdir(parents=True, exist_ok=True)
        staging = self.folder / f".staging-{plugin}"
        target = self.folder / plugin
        shutil.rmtree(staging, ignore_errors=True)
        try:
            for path, data in files:
                file = staging / path
                file.parent.mkdir(parents=True, exist_ok=True)
                file.write_bytes(data)
            manifest = load_manifest(staging)
            # Was der Zustimmungsdialog gezeigt hat (Katalog), ist, was das Manifest gewährt
            if (manifest["id"] != plugin or manifest.get("version") != entry.get("version")
                    or sorted(entry.get("permissions") or []) != sorted(manifest.get("permissions") or [])):
                raise PluginError(f"{entry.get('name')}: Manifest passt nicht zum Katalog")
            if target.is_dir():
                try:
                    old = load_manifest(target)
                except PluginError:
                    old = None
                if old and newer(str(old.get("version")), str(entry.get("version"))):
                    raise PluginError(f"{entry.get('name')} {old.get('version')} ist neuer als der Katalog")
                shutil.rmtree(target)
            staging.rename(target)
        finally:
            shutil.rmtree(staging, ignore_errors=True)
        proof = self._proof(plugin)
        proof.parent.mkdir(parents=True, exist_ok=True)
        _, _, index, signature = self._catalog
        proof.write_text(json.dumps({"index": index, "signature": signature}))

    async def uninstall(self, plugin: str) -> dict:
        self._require_id(plugin)
        await self._overlay({"action": "close", "id": plugin})
        await self._drop_widgets(plugin)
        self._remember_window(plugin, None)
        self.logs.pop(plugin, None)
        self._save_list(DISABLED_KEY, [x for x in self.disabled() if x != plugin])
        shutil.rmtree(self.folder / plugin, ignore_errors=True)
        self._proof(plugin).unlink(missing_ok=True)
        await self._forget_follows(plugin)
        self.reload()
        await self.send_decoders()
        if plugin in EMBEDDED:
            await self.emit("plugin-embed", {"plugin": plugin, "shown": False})
        return self.view()  # gespeicherte Daten bleiben für eine spätere Installation

    async def check_updates(self) -> dict:
        self.reload()
        available, error = [], None
        try:
            catalog = await self.fetch_catalog()
            for entry in catalog.get("plugins", []):
                p = self.loaded.get(entry.get("id"))
                if p and newer(str(entry.get("version")), str(p.manifest.get("version"))):
                    frm, to = str(p.manifest.get("version")), str(entry.get("version"))
                    available.append({
                        "id": p.id, "name": entry.get("name"), "from": frm, "to": to,
                        "newPermissions": [x for x in entry.get("permissions") or [] if x not in p.permissions],
                        "changes": [c for c in entry.get("changes") or []
                                    if newer(str(c.get("version")), frm) and not newer(str(c.get("version")), to)]})
        except (PluginError, aiohttp.ClientError, TimeoutError, ValueError) as e:
            error = str(e)
        return {"view": self.view(), "updated": [], "available": available, "catalogError": error}

    # ------------------------------------------------------------ Fenster
    async def _overlay(self, command: dict) -> None:
        if self.overlay is None:
            return
        try:
            await self.overlay(command)
        except RuntimeError as e:  # Overlay läuft gerade nicht: beim nächsten Start aus plugin_windows
            log.debug("Plugin-Fenster %s: %s", command, e)

    def _window_info(self, plugin: str) -> dict:
        p = self.loaded[plugin]
        panel = (p.manifest.get("ui") or {}).get("panel") or {}

        def dim(key: str, default: float, low: float) -> float:
            value = panel.get(key)
            return max(low, min(float(value) if isinstance(value, (int, float)) else default, 1200.0))

        width, height = dim("width", 360.0, 240.0), dim("height", 480.0, MIN_PANEL_HEIGHT)
        return {"id": plugin, "name": p.manifest.get("name", plugin), "width": width, "height": height + 30,
                "minWidth": 240, "minHeight": min(height + 30, 230)}

    async def _open(self, plugin: str, shown: bool) -> None:
        if plugin in EMBEDDED:
            await self.emit("plugin-embed", {"plugin": plugin, "shown": shown})
            return
        await self._overlay({"action": "open", "shown": shown, **self._window_info(plugin)})
        await self.emit("plugin-event", {"plugin": plugin, "event": "visible", "data": shown})

    def windows_to_restore(self) -> list[dict]:
        """Für den Start des Overlays: jedes eingeschaltete Plugin läuft, sichtbar wie zuletzt."""
        windows = self._windows()
        return [{**self._window_info(p), "shown": windows.get(p) == "shown"} for p in self._on_ids() if p not in EMBEDDED]

    def embedded(self) -> list[str]:
        """Für die Overlay-Seite: welche Plugins sie selbst trägt."""
        return [p for p in self._on_ids() if p in EMBEDDED]

    def _require_id(self, plugin: str) -> None:
        if not valid_id(plugin):
            raise PluginError("keine Plugin-Kennung")

    def _plugin_of(self, window: str | None) -> str:
        """Das Plugin einer aufrufenden Seite, allein aus ihrer Fensterkennung."""
        window = window or ""
        if window.startswith("plugin-"):
            plugin = window[7:]
        elif window.startswith("widget:"):
            plugin = window.split(":")[1]
        else:
            raise PluginError("kein Plugin-Fenster")
        if plugin not in self.loaded:
            raise PluginError("Plugin nicht geladen")
        return plugin

    def _require(self, plugin: str, permission: str) -> None:
        p = self.loaded.get(plugin)
        if p is None or permission not in p.permissions:
            raise PluginError(f"dem Plugin fehlt die Berechtigung {permission}")

    async def _set_enabled(self, plugin: str, enabled: bool) -> dict:
        self._require_id(plugin)
        ids = [x for x in self.disabled() if x != plugin]
        if not enabled:
            ids.append(plugin)
        self._save_list(DISABLED_KEY, ids)
        if enabled:
            self._remember_window(plugin, "shown")
            if plugin in self.loaded:
                await self._open(plugin, True)
        else:
            await self._overlay({"action": "close", "id": plugin})
            await self._drop_widgets(plugin)
            await self._forget_follows(plugin)
            self.pending[:] = [p for p in self.pending if p.plugin != plugin]
            self.logs.pop(plugin, None)
            if plugin in EMBEDDED:
                await self.emit("plugin-embed", {"plugin": plugin, "shown": False})
        await self.send_decoders()
        return self.view()

    # ------------------------------------------------------------ Widgets
    def _locked_key(self, plugin: str) -> str:
        return f"dpsMeter.pluginWidgetsLocked.{plugin}"

    def _locked(self, plugin: str) -> bool:
        return self.settings().get(self._locked_key(plugin)) == "true"

    def widgets_state(self) -> list[dict]:
        return [{"label": w.label, "plugin": w.plugin, "name": w.name, "width": w.width, "height": w.height,
                 "x": w.x, "y": w.y, "open": w.open, "areas": w.areas, "locked": self._locked(w.plugin)}
                for w in self.widgets.values()]

    async def _publish_widgets(self) -> None:
        await self.emit("plugin-widgets", self.widgets_state())

    async def _drop_widgets(self, plugin: str) -> None:
        gone = [k for k, w in self.widgets.items() if w.plugin == plugin]
        for key in gone:
            del self.widgets[key]
        if gone:
            await self._publish_widgets()

    def _place_key(self, plugin: str, name: str) -> str:
        return f"dpsMeter.pluginWidget.{plugin}.{name}"

    def _on_screen(self, x: int, y: int, width: float, height: float) -> tuple[int, int]:
        return (max(0, min(x, int(self.screen["width"] - min(width, self.screen["width"])))),
                max(0, min(y, int(self.screen["height"] - min(height, self.screen["height"])))))

    def _first_place(self, plugin: str, name: str, width: float, height: float) -> tuple[int, int]:
        """Wo es zuletzt lag, sonst neben den anderen des Plugins, sonst ein freier Platz am rechten Rand."""
        saved = self.settings().get(self._place_key(plugin, name), "")
        m = re.fullmatch(r"(-?\d+),(-?\d+)", saved)
        if m:
            return self._on_screen(int(m[1]), int(m[2]), width, height)
        others = [w for w in self.widgets.values() if w.plugin == plugin]
        if others:
            last = others[-1]
            return self._on_screen(int(last.x + last.width + 4), last.y, width, height)
        taken = len({w.plugin for w in self.widgets.values()})
        return self._on_screen(int(self.screen["width"] - width - 40), 160 + 90 * taken, width, height)

    async def _widget_open(self, plugin: str, a: dict) -> None:
        self._require(plugin, "widgets")
        if plugin in self.disabled():
            raise PluginError("Dieses Plugin ist ausgeschaltet")
        name = str(a.get("name"))
        if not WIDGET_NAME.fullmatch(name):
            raise PluginError("Ein Widget-Name hat 1 bis 32 Kleinbuchstaben, Ziffern oder '-'")

        def size(v: Any) -> float:
            v = float(v) if isinstance(v, (int, float)) else 64.0
            return max(24.0, min(v, 800.0))

        width, height = size(a.get("width")), size(a.get("height"))
        key = f"widget:{plugin}:{name}"
        w = self.widgets.get(key)
        if w:
            w.width, w.height, w.open = width, height, True
            w.x, w.y = self._on_screen(w.x, w.y, width, height)
        else:
            mine = [k for k, x in self.widgets.items() if x.plugin == plugin]
            if len(mine) >= MAX_WIDGETS:
                spare = next((k for k in mine if not self.widgets[k].open), None)
                if spare is None:
                    raise PluginError(f"höchstens {MAX_WIDGETS} Widgets")
                del self.widgets[spare]
            x, y = self._first_place(plugin, name, width, height)
            self.widgets[key] = WidgetState(plugin, name, width, height, x, y)
        await self._publish_widgets()

    async def _widget_moved(self, label: str, x: int, y: int) -> None:
        """Die Overlay-Seite meldet, wohin ein Widget gezogen wurde."""
        w = self.widgets.get(label)
        if w is None:
            return
        w.x, w.y = self._on_screen(x, y, w.width, w.height)
        self.save_setting(self._place_key(w.plugin, w.name), f"{w.x},{w.y}")
        await self.emit("plugin-event", {"plugin": w.plugin, "event": "widget-moved",
                                         "data": {"name": w.name, "x": w.x, "y": w.y}})
        await self._publish_widgets()

    # ------------------------------------------------------------ Boss-Daten (online)
    async def _feed(self, feed: str, server: int) -> Any:
        if not 1000 <= server < 10000:
            raise PluginError("keine Server-Kennung")
        key = (feed, server)
        now = time.monotonic()
        cached = self._feeds.get(key)
        if cached and now - cached[0] < FEED_CACHE:
            return cached[1]
        http = await self._session()
        try:
            async with http.get(f"{FEED_URL}/{feed}/{server}.json", timeout=aiohttp.ClientTimeout(total=15)) as r:
                if r.status == 404:
                    value = None
                elif r.status == 200:
                    value = json.loads(await r.read())
                else:
                    raise PluginError(f"Der Feed antwortete {r.status}")
        except (aiohttp.ClientError, TimeoutError, ValueError) as e:
            raise PluginError(str(e)) from e
        self._feeds[key] = (now, value)
        return value

    def _wanted(self, server: int) -> list[str]:
        return sorted({b for (_, s), bosses in self._follows.items() if s == server for b in bosses})

    async def _boss_follow(self, plugin: str, server: int, bosses: list) -> None:
        if not 1000 <= server < 10000:
            raise PluginError("keine Server-Kennung")
        clean = {str(b) for b in bosses if isinstance(b, (str, int)) and str(b).isdigit() and len(str(b)) <= 16}
        clean = set(sorted(clean)[:MAX_FOLLOW])
        if clean:
            self._follows[(plugin, server)] = clean
        else:
            self._follows.pop((plugin, server), None)
        self._apply_follows(server)

    def _apply_follows(self, server: int) -> None:
        if self._wanted(server):
            task = self._live.get(server)
            if task is None or task.done():
                self._live_wanted[server] = asyncio.Event()
                self._live[server] = asyncio.create_task(self._live_run(server))
            else:
                self._live_wanted[server].set()
        elif server in self._live:
            self._live.pop(server).cancel()
            self._live_wanted.pop(server, None)

    async def _forget_follows(self, plugin: str) -> None:
        servers = [s for p, s in self._follows if p == plugin]
        for server in servers:
            self._follows.pop((plugin, server), None)
            self._apply_follows(server)

    async def _live_run(self, server: int) -> None:
        """Eine Verbindung je Server, solange etwas verfolgt wird, sonst nur die Feed-Datei."""
        backoff = 2.0
        changed = self._live_wanted[server]
        while self._wanted(server):
            try:
                http = await self._session()
                async with http.ws_connect(f"{LIVE_URL}?server={server}", timeout=aiohttp.ClientWSTimeout(ws_close=15),
                                           max_msg_size=1 << 20) as ws:
                    backoff = 2.0
                    follow = self._wanted(server)
                    await ws.send_str(json.dumps({"op": "follow", "bosses": follow}))
                    await self.tell_permitted("feed:boss-timers", "bossLive",
                                              {"type": "status", "server": server, "connected": True})
                    last_ping = time.monotonic()
                    heard = last_ping
                    while True:
                        if changed.is_set():
                            changed.clear()
                            if self._wanted(server) != follow:
                                follow = self._wanted(server)
                                await ws.send_str(json.dumps({"op": "follow", "bosses": follow}))
                        if time.monotonic() - last_ping >= 30:
                            await ws.send_str("ping")
                            last_ping = time.monotonic()
                        if time.monotonic() - heard >= 75:
                            break  # zwei Pings ohne Antwort: Verbindung tot
                        try:
                            msg = await ws.receive(timeout=5)
                        except TimeoutError:
                            continue
                        if msg.type == aiohttp.WSMsgType.TEXT:
                            heard = time.monotonic()
                            if msg.data == "pong":
                                continue
                            data = json.loads(msg.data)
                            if isinstance(data, dict):
                                await self.tell_permitted("feed:boss-timers", "bossLive", {**data, "server": server})
                        elif msg.type in (aiohttp.WSMsgType.CLOSE, aiohttp.WSMsgType.CLOSED, aiohttp.WSMsgType.ERROR):
                            if ws.close_code == 4004:
                                return  # Diesen Server führt die Seite nicht
                            break
            except asyncio.CancelledError:
                raise
            except (aiohttp.ClientError, TimeoutError, ValueError, OSError) as e:
                log.debug("Boss live %s: %s", server, e)
            await self.tell_permitted("feed:boss-timers", "bossLive",
                                      {"type": "status", "server": server, "connected": False})
            await asyncio.sleep(backoff)
            backoff = min(backoff * 2, 60.0)

    # ------------------------------------------------------------ Speicher
    def _data_file(self, plugin: str, key: str) -> Path:
        if not STORAGE_KEY.fullmatch(key):
            raise PluginError("Speicher-Schlüssel: Buchstaben, Ziffern, '-' und '_'")
        return self.data_folder / plugin / f"{key}.json"

    def _storage_set(self, plugin: str, key: str, value: str) -> None:
        if len(value.encode()) > MAX_STORED:
            raise PluginError("Wert größer als 1 MB")
        file = self._data_file(plugin, key)
        file.parent.mkdir(parents=True, exist_ok=True)
        if not file.exists() and sum(1 for _ in file.parent.iterdir()) >= MAX_STORED_KEYS:
            raise PluginError(f"höchstens {MAX_STORED_KEYS} Speicher-Schlüssel")
        tmp = file.with_suffix(".tmp")
        tmp.write_text(value, encoding="utf-8")
        os.replace(tmp, file)

    # ------------------------------------------------------------ Befehle der Oberfläche
    def _hello(self, plugin: str) -> dict:
        p = self.loaded[plugin]
        replay = [json.loads(t) for t in self.logs[plugin].events] if plugin in self.logs else []
        ping = self.capture.status.get("ping")
        return {"manifest": p.public(), "replay": replay, "run": self.run,
                "character": self.character if "events:character" in p.permissions else None,
                "language": self.language(), "theme": self.theme(),
                "visible": plugin in EMBEDDED or self._windows().get(plugin) == "shown",
                "reviewed": True, "game": bool(self.capture.status.get("game")),
                "ping": ping if isinstance(ping, (int, float)) else None}

    async def call(self, cmd: str, a: dict, window: str | None) -> Any:
        """Ein Befehl von einer Seite. `window`: die Fensterkennung, die das Shim mitschickt."""
        if window and window.startswith(("plugin-", "widget:")) and cmd not in SURFACE:
            raise PluginError(f"{cmd}: für Plugins nicht erlaubt")
        match cmd:
            case "plugin_list" | "plugin_set_dev_mode" | "plugin_add_folder" | "plugin_remove_folder":
                return self.view()  # Entwickler-Ordner gibt es hier nicht, nur den signierten Katalog
            case "plugin_catalog":
                try:
                    return await self.catalog_items()
                except (aiohttp.ClientError, TimeoutError) as e:
                    raise PluginError(str(e)) from e
            case "plugin_install":
                return await self.install(str(a.get("id")))
            case "plugin_uninstall":
                return await self.uninstall(str(a.get("id")))
            case "plugin_check_updates":
                return await self.check_updates()
            case "plugin_pending_updates":
                return []
            case "plugin_set_enabled":
                return await self._set_enabled(str(a.get("id")), bool(a.get("enabled")))
            case "plugin_set_hide":
                plugin = str(a.get("id"))
                self._require_id(plugin)
                key = {"closed": HIDE_CLOSED_KEY, "unfocused": HIDE_UNFOCUSED_KEY}.get(str(a.get("when")))
                if key is None:
                    raise PluginError("closed oder unfocused")
                ids = [x for x in self._listed(key) if x != plugin]
                if a.get("hide"):
                    ids.append(plugin)
                self._save_list(key, ids)
                return self.view()
            case "plugin_open":
                plugin = str(a.get("id"))
                if plugin not in self.loaded:
                    raise PluginError("Plugin nicht geladen")
                self._remember_window(plugin, "shown")
                await self._open(plugin, True)
                return None
            case "plugin_set_docked" | "set_meter_shown":
                return None
            case "meter_shown":
                return True
            case "set_plugin_theme":
                theme = clean_theme(a.get("theme"))
                if theme is None:
                    raise PluginError("kein Farbschema")
                if theme != self.theme():
                    self.save_setting(THEME_KEY, json.dumps(theme))
                    await self.tell_all("theme", theme)
                return None
            case "plugin_windows":
                return self.windows_to_restore()
            case "plugin_widgets_state":
                return self.widgets_state()
            case "plugin_embedded":
                return self.embedded()
            case "plugin_overlay_screen":
                self.screen = {"width": max(320, int(a.get("width") or 1920)), "height": max(240, int(a.get("height") or 1080))}
                return None
            case "plugin_widget_moved":
                await self._widget_moved(str(a.get("label")), int(a.get("x") or 0), int(a.get("y") or 0))
                return None
        plugin = self._plugin_of(window)
        match cmd:
            case "plugin_hello":
                if a.get("fresh"):  # Ein frisch startendes Plugin kennt alte Widgets nicht und schlösse sie nie
                    await self._drop_widgets(plugin)
                return self._hello(plugin)
            case "plugin_window":
                visible = bool(a.get("visible"))
                self._require(plugin, "window")
                if plugin in EMBEDDED:
                    # Klick auf die Würfelkarte: zum Reiter; sich selbst nach vorn holen darf kein Plugin im Radar
                    if visible and plugin == "dice-rolls":
                        await self.emit("plugin-embed", {"plugin": plugin, "shown": True})
                    return None
                self._remember_window(plugin, "shown" if visible else "hidden")
                await self._overlay({"action": "show" if visible else "hide", "id": plugin})
                await self.emit("plugin-event", {"plugin": plugin, "event": "visible", "data": visible})
                return None
            case "plugin_close":
                if plugin in EMBEDDED:
                    return None
                self._remember_window(plugin, "hidden")
                await self._overlay({"action": "hide", "id": plugin})
                await self.emit("plugin-event", {"plugin": plugin, "event": "visible", "data": False})
                return None
            case "plugin_window_fit":
                self._require(plugin, "window")
                if plugin in EMBEDDED:
                    return None
                height = a.get("height")
                await self._overlay({"action": "fit", "id": plugin,
                                     "height": max(MIN_PANEL_HEIGHT, float(height)) if isinstance(height, (int, float)) else None})
                return None
            case "plugin_storage_get":
                self._require(plugin, "storage")
                key = str(a.get("key"))
                try:
                    text = self._data_file(plugin, key).read_text(encoding="utf-8")
                except FileNotFoundError:
                    text = None
                if key == "prefs" and plugin in EMBEDDED_PREFS:
                    return json.dumps({**json.loads(text or "{}"), **EMBEDDED_PREFS[plugin]})
                return text
            case "plugin_storage_set":
                self._require(plugin, "storage")
                self._storage_set(plugin, str(a.get("key")), str(a.get("value")))
                return None
            case "plugin_boss_timers":
                self._require(plugin, "feed:boss-timers")
                return await self._feed("boss-timers", int(a.get("server") or 0))
            case "plugin_abyss_siege":
                self._require(plugin, "feed:boss-timers")
                return await self._feed("abyss-artifacts", int(a.get("server") or 0))
            case "plugin_boss_follow":
                self._require(plugin, "feed:boss-timers")
                await self._boss_follow(plugin, int(a.get("server") or 0), list(a.get("bosses") or []))
                return None
            case "plugin_fps_watch":
                self._require(plugin, "fps")
                return {"fps": None, "state": "unsupported"}  # Die Zählung gibt es nur im Windows-Meter
            case "plugin_fps_admin":
                self._require(plugin, "fps")
                return False
            case "plugin_widget_open":
                await self._widget_open(plugin, a)
                return None
            case "plugin_widget_close":
                self._require(plugin, "widgets")
                if w := self.widgets.get(f"widget:{plugin}:{a.get('name')}"):
                    w.open = False
                    await self._publish_widgets()
                return None
            case "plugin_widget_send":
                self._require(plugin, "widgets")
                data = a.get("data")
                if len(json.dumps(data)) > MAX_MESSAGE:
                    raise PluginError("Nachricht zu groß")
                await self.emit("plugin-event", {"plugin": plugin, "event": "widget", "data": data,
                                                 "__window": f"widget:{plugin}:{a.get('name')}"})
                return None
            case "plugin_widgets_lock":
                self._require(plugin, "widgets")
                locked = bool(a.get("locked"))
                self.save_setting(self._locked_key(plugin), "true" if locked else "false")
                await self.emit("plugin-event", {"plugin": plugin, "event": "locked", "data": locked})
                await self._publish_widgets()
                return None
            case "plugin_widgets_locked":
                self._require(plugin, "widgets")
                return self._locked(plugin)
            case "plugin_widget_where":
                self._require(plugin, "widgets")
                w = self.widgets.get(f"widget:{plugin}:{a.get('name')}")
                if w is None:
                    return None
                return {"x": w.x, "y": w.y, "width": int(w.width), "height": int(w.height),
                        "screen": {"x": 0, "y": 0, **self.screen}}
            case "plugin_widget_place":
                self._require(plugin, "widgets")
                name = str(a.get("name"))
                if not WIDGET_NAME.fullmatch(name):
                    raise PluginError("Ein Widget-Name hat 1 bis 32 Kleinbuchstaben, Ziffern oder '-'")
                x, y = int(a.get("x") or 0), int(a.get("y") or 0)
                w = self.widgets.get(f"widget:{plugin}:{name}")
                x, y = self._on_screen(x, y, w.width if w else 64, w.height if w else 64)
                self.save_setting(self._place_key(plugin, name), f"{x},{y}")
                if w:
                    w.x, w.y = x, y
                    await self._publish_widgets()
                return None
            case "plugin_widget_hello":
                if not (window or "").startswith("widget:"):
                    raise PluginError("kein Widget-Fenster")
                name = (window or "").split(":")[2]
                return {"plugin": plugin, "name": name, "locked": self._locked(plugin), "language": self.language()}
            case "plugin_widget_post":
                if not (window or "").startswith("widget:"):
                    raise PluginError("kein Widget-Fenster")
                data = a.get("data")
                if len(json.dumps(data)) > MAX_MESSAGE:
                    raise PluginError("Nachricht zu groß")
                await self.emit("plugin-event", {"plugin": plugin, "event": "widget-message",
                                                 "data": {"name": (window or "").split(":")[2], "data": data}})
                return None
            case "plugin_widget_area":
                w = self.widgets.get(window or "")
                if w is None:
                    raise PluginError("kein Widget-Fenster")
                rects = a.get("rects")
                if not isinstance(rects, list) or len(rects) > MAX_AREAS:
                    raise PluginError("keine Fläche")
                w.areas = [[float(r["x"]), float(r["y"]), float(r["width"]), float(r["height"])] for r in rects]
                await self._publish_widgets()
                return None
        raise PluginError(f"{cmd}: im NexBoard nicht verfügbar")


def clean_theme(theme: Any) -> dict | None:
    """Genau die drei Farben, je #rrggbb: sie landen als CSS auf den Plugin-Seiten."""
    if not isinstance(theme, dict):
        return None
    colors = {k: theme.get(k) for k in ("bg", "panel", "accent")}
    return colors if all(isinstance(c, str) and HEX_COLOR.fullmatch(c) for c in colors.values()) else None


# ---------------------------------------------------------------- Auslieferung der Plugin-Dateien
FONTS = Path(__file__).resolve().parents[2] / "capture" / "a2tools" / "src-tauri" / "src" / "plugins" / "fonts"
TEXT_RANGE = ("font-weight:45 920;unicode-range:U+0000-00FF,U+0131,U+0152-0153,U+02BB-02BC,U+02C6,U+02DA,U+02DC,"
              "U+2000-206F,U+2074,U+20AC,U+2122,U+2190-2199,U+2212,U+2215;")
_font_style: str | None = None


def font_style() -> str:
    """Die Schriften des Meters, die Plugin-Seiten erwarten (wie with_meter_fonts im Original)."""
    global _font_style
    if _font_style is None:
        def face(family: str, file: str, extra: str) -> str:
            try:
                data = base64.b64encode((FONTS / file).read_bytes()).decode()
            except OSError:
                return ""
            return f'@font-face{{font-family:"{family}";src:url(data:font/woff2;base64,{data}) format("woff2");{extra}}}'
        _font_style = "<style>" + face("Pretendard", "PretendardLatin.woff2", TEXT_RANGE) \
            + face("Segoe UI", "PretendardLatin.woff2", TEXT_RANGE) \
            + face("Bahnschrift", "Saira.woff2", "font-weight:100 900;font-stretch:50% 125%;") + "</style>"
    return _font_style


def with_fonts(page: str) -> str:
    i = page.lower().find("<head")
    at = page.find(">", i) + 1 if i >= 0 else 0
    return page[:at] + font_style() + page[at:]


def content_policy(origin: str, prefix: str, plugin: str) -> str:
    """Nur der eigene Ordner und das SDK, kein Netz (content_policy im Original)."""
    own = f"'self' {origin}/_sdk/a2.js"
    if valid_id(plugin):
        own += f" {origin}{prefix}{plugin}/"
    return (f"default-src 'none'; script-src {own}; style-src {own} 'unsafe-inline'; img-src {own} data:; "
            f"font-src {own} data:; media-src {own}; connect-src 'none'; frame-src 'none'; base-uri 'none'; "
            "form-action 'none'")
