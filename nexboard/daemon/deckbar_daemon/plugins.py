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

from .plugin_catalog import PluginCatalog
from .plugin_commands import (
    HIDE_CLOSED_KEY,
    HIDE_UNFOCUSED_KEY,
    MIN_PANEL_HEIGHT,
    THEME_KEY,
    WIDGET_NAME,
    PluginCommands,
)
from .plugin_feeds import BossFeeds
from .plugin_files import (
    PUBLIC_KEY_HEX,
    PluginError,
    load_manifest,
    newer,
    valid_id,
)
from .plugin_page import clean_theme

log = logging.getLogger(__name__)

BASE_URL = "https://cdn.a2tools.app/plugins"
CATALOG_MAX_AGE = 300.0

MAX_STORED = 1024 * 1024
MAX_STORED_KEYS = 256
MAX_WIDGETS = 16
SETTLE = 0.5  # Decoder-Ereignisse warten auf den Charakter (beim Login kommt er erst danach)
BATCH_WAIT = 0.04
MAX_LOGGED = 20_000
MAX_LOGGED_BYTES = 2 * 1024 * 1024
GAME_CHECK = 5.0

WINDOWS_KEY = "dpsMeter.pluginWindows"
DISABLED_KEY = "dpsMeter.pluginsDisabled"
DEFAULT_THEME = {"bg": "#0a0e16", "panel": "#0a0e16", "accent": "#8fc2ff"}
LANGUAGE_KEY = "dpsMeter.language"
STORAGE_KEY = re.compile(r"[A-Za-z0-9_-]{1,64}")

# Nummerierte Ereignisse aus deckbar-capture (feed.rs) → Recht, das ein Plugin dafür braucht (wie mod.rs im Meter)
NUMBERED_FEEDS = {"deathRecap": "events:death-recap", "lootRoll": "events:loot-rolls",
                  "blackMarket": "events:black-market", "kda": "events:kda"}


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


class PluginHost(PluginCommands):
    def __init__(self, capture: Any, settings: Callable[[], dict[str, str]], save_setting: Callable[[str, str], None],
                 emit: Callable[[str, Any], Awaitable[None]], folder: Path, data_folder: Path,
                 base_url: str = BASE_URL, key_hex: str = PUBLIC_KEY_HEX) -> None:
        self.capture = capture
        self.settings = settings
        self.save_setting = save_setting
        self.emit = emit
        self.folder = folder
        self.data_folder = data_folder
        self.catalog = PluginCatalog(folder, base_url, key_hex, self._session)
        self.overlay: Callable[[dict], Awaitable[None]] | None = None  # Befehle ans Overlay-Programm
        # Stand der Plugin-Widgets für die Overlay-Seite (ihre eine Ereignisverbindung)
        self.widgets_listener: Callable[[list[dict]], Awaitable[None]] | None = None
        self.loaded: dict[str, Loaded] = {}
        self.errors: dict[str, dict] = {}
        self.decoder_errors: dict[str, str] = {}
        self.active = False  # Modul AION 2 · Plugins an: Plugins laufen und bekommen Spieldaten
        self.widgets: dict[str, WidgetState] = {}
        self.pending: list[Pending] = []
        self.logs: dict[str, EventLog] = {}
        self.run = str(int(time.time() * 1000))
        # Zählt über Neustarts hinweg weiter: offene Seiten merken sich die letzte Nummer
        self.seq = int(time.time() * 1000)
        self.character: Any = None
        self.screen = {"width": 1920, "height": 1080}
        self.game = False
        self.feeds = BossFeeds(self._session, lambda event, data: self.tell_permitted("feed:boss-timers", event, data))
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
                self.catalog.verify_installed(manifest["id"], folder, str(manifest.get("version", "")))
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
                   for p in self.loaded.values() if self.active and p.id not in off]
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
        self.active = True
        if not self._tasks:
            self._tasks = [asyncio.create_task(self._flusher()), asyncio.create_task(self._game_loop())]

    async def deactivate(self) -> None:
        """Modul aus: Fenster und Widgets zu, keine Spieldaten mehr. Installiert bleibt alles."""
        self.active = False
        for plugin in self.loaded:
            await self._overlay({"action": "close", "id": plugin})
            await self._drop_widgets(plugin)
        await self.stop()
        await self.send_decoders()

    async def stop(self) -> None:
        for task in self._tasks:
            task.cancel()
        await asyncio.gather(*self._tasks, return_exceptions=True)
        self._tasks = []
        await self.feeds.stop()
        if self._http:
            await self._http.close()
            self._http = None

    # ------------------------------------------------------------ Ereignisse aus dem Mitschnitt
    async def _on_capture(self, event: str, payload: Any) -> None:
        if event == "hello" and self.active:
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
        permission = NUMBERED_FEEDS.get(event)
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

    async def catalog_items(self) -> list[dict]:
        catalog = await self.catalog.fetch(CATALOG_MAX_AGE)
        return [{"id": e.get("id"), "name": e.get("name"), "version": e.get("version"),
                 "description": e.get("description", ""), "author": e.get("author", ""),
                 "permissions": e.get("permissions") or [], "source": e.get("source", ""),
                 "installed": self.loaded[e["id"]].manifest.get("version") if e.get("id") in self.loaded else None,
                 "test": False, "changes": e.get("changes") or []}
                for e in catalog.get("plugins", [])]

    async def install(self, plugin: str) -> dict:
        plugin = plugin.strip().lower()
        catalog = await self.catalog.fetch()
        entry = next((e for e in catalog.get("plugins", []) if e.get("id") == plugin), None)
        if entry is None:
            raise PluginError("Dieses Plugin steht nicht im Katalog")
        files = await self.catalog.download(entry)
        await self.emit("plugin-install-phase", {"id": plugin, "phase": "installing"})
        updating = plugin in self.loaded
        await asyncio.to_thread(self.catalog.write, entry, files)
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

    async def uninstall(self, plugin: str) -> dict:
        self._require_id(plugin)
        await self._overlay({"action": "close", "id": plugin})
        await self._drop_widgets(plugin)
        self._remember_window(plugin, None)
        self.logs.pop(plugin, None)
        self._save_list(DISABLED_KEY, [x for x in self.disabled() if x != plugin])
        shutil.rmtree(self.folder / plugin, ignore_errors=True)
        self.catalog.proof(plugin).unlink(missing_ok=True)
        await self.feeds.forget(plugin)
        self.reload()
        await self.send_decoders()
        return self.view()  # gespeicherte Daten bleiben für eine spätere Installation

    async def check_updates(self) -> dict:
        self.reload()
        available, error = [], None
        try:
            catalog = await self.catalog.fetch()
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
        await self._overlay({"action": "open", "shown": shown, **self._window_info(plugin)})
        await self.emit("plugin-event", {"plugin": plugin, "event": "visible", "data": shown})

    def windows_to_restore(self) -> list[dict]:
        """Für den Start des Overlays: jedes eingeschaltete Plugin läuft, sichtbar wie zuletzt."""
        windows = self._windows()
        return [{**self._window_info(p), "shown": windows.get(p) == "shown"} for p in self._on_ids()]

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
            await self.feeds.forget(plugin)
            self.pending[:] = [p for p in self.pending if p.plugin != plugin]
            self.logs.pop(plugin, None)
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
        if self.widgets_listener:
            await self.widgets_listener(self.widgets_state())

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
                "visible": self._windows().get(plugin) == "shown",
                "reviewed": True, "game": bool(self.capture.status.get("game")),
                "ping": ping if isinstance(ping, (int, float)) else None}
