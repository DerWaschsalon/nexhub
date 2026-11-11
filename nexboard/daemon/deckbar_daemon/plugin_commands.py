"""Befehle der Plugin-Seiten an den Host: eine Tabelle Befehl → Methode statt einer langen Verzweigung.

host_command: Befehle der eigenen Oberfläche (Plugin-Verwaltung, Overlay). plugin_command: Befehle eines
Plugins; der Verteiler ermittelt das Plugin aus der Fensterkennung und prüft das verlangte Recht.
PluginCommands ist der Befehlsteil von PluginHost (plugins.py) und nutzt dessen Zustand und Helfer.
"""
from __future__ import annotations

import json
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from typing import Any

import aiohttp

from .plugin_files import PluginError
from .plugin_page import clean_theme

MAX_MESSAGE = 64 * 1024
MIN_PANEL_HEIGHT = 60.0
HIDE_CLOSED_KEY = "dpsMeter.pluginsHideClosed"
HIDE_UNFOCUSED_KEY = "dpsMeter.pluginsHideUnfocused"
THEME_KEY = "dpsMeter.pluginTheme"
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


@dataclass(frozen=True)
class Command:
    handler: Callable[..., Awaitable[Any]]
    needs_plugin: bool
    permission: str | None = None  # Recht aus dem Manifest, das der Verteiler vorab prüft


COMMANDS: dict[str, Command] = {}


def host_command(*names: str):
    def register(handler):
        COMMANDS.update({n: Command(handler, needs_plugin=False) for n in names})
        return handler
    return register


def plugin_command(*names: str, permission: str | None = None):
    def register(handler):
        COMMANDS.update({n: Command(handler, needs_plugin=True, permission=permission) for n in names})
        return handler
    return register


def _widget_name(window: str | None) -> str:
    if not (window or "").startswith("widget:"):
        raise PluginError("kein Widget-Fenster")
    return (window or "").split(":")[2]


def _message(a: dict) -> Any:
    data = a.get("data")
    if len(json.dumps(data)) > MAX_MESSAGE:
        raise PluginError("Nachricht zu groß")
    return data


class PluginCommands:
    async def call(self, cmd: str, a: dict, window: str | None) -> Any:
        """Ein Befehl von einer Seite. `window`: die Fensterkennung, die das Shim mitschickt."""
        if window and window.startswith(("plugin-", "widget:")) and cmd not in SURFACE:
            raise PluginError(f"{cmd}: für Plugins nicht erlaubt")
        command = COMMANDS.get(cmd)
        if command and not command.needs_plugin:
            return await command.handler(self, a)
        plugin = self._plugin_of(window)
        if command is None:
            raise PluginError(f"{cmd}: im NexBoard nicht verfügbar")
        if command.permission:
            self._require(plugin, command.permission)
        return await command.handler(self, plugin, a, window)

    # ------------------------------------------------------------ eigene Oberfläche
    @host_command("plugin_list", "plugin_set_dev_mode", "plugin_add_folder", "plugin_remove_folder")
    async def _cmd_list(self, a: dict) -> dict:
        return self.view()  # Entwickler-Ordner gibt es hier nicht, nur den signierten Katalog

    @host_command("plugin_catalog")
    async def _cmd_catalog(self, a: dict) -> list[dict]:
        try:
            return await self.catalog_items()
        except (aiohttp.ClientError, TimeoutError) as e:
            raise PluginError(str(e)) from e

    @host_command("plugin_install")
    async def _cmd_install(self, a: dict) -> dict:
        return await self.install(str(a.get("id")))

    @host_command("plugin_uninstall")
    async def _cmd_uninstall(self, a: dict) -> dict:
        return await self.uninstall(str(a.get("id")))

    @host_command("plugin_check_updates")
    async def _cmd_check_updates(self, a: dict) -> dict:
        return await self.check_updates()

    @host_command("plugin_pending_updates")
    async def _cmd_pending_updates(self, a: dict) -> list:
        return []

    @host_command("plugin_set_enabled")
    async def _cmd_set_enabled(self, a: dict) -> Any:
        return await self._set_enabled(str(a.get("id")), bool(a.get("enabled")))

    @host_command("plugin_set_hide")
    async def _cmd_set_hide(self, a: dict) -> dict:
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

    @host_command("plugin_open")
    async def _cmd_open(self, a: dict) -> None:
        plugin = str(a.get("id"))
        if plugin not in self.loaded:
            raise PluginError("Plugin nicht geladen")
        self._remember_window(plugin, "shown")
        await self._open(plugin, True)

    @host_command("plugin_set_docked", "set_meter_shown")
    async def _cmd_ignored(self, a: dict) -> None:
        return None

    @host_command("meter_shown")
    async def _cmd_meter_shown(self, a: dict) -> bool:
        return True

    @host_command("set_plugin_theme")
    async def _cmd_set_theme(self, a: dict) -> None:
        theme = clean_theme(a.get("theme"))
        if theme is None:
            raise PluginError("kein Farbschema")
        if theme != self.theme():
            self.save_setting(THEME_KEY, json.dumps(theme))
            await self.tell_all("theme", theme)

    @host_command("plugin_windows")
    async def _cmd_windows(self, a: dict) -> list[dict]:
        return self.windows_to_restore()

    @host_command("plugin_widgets_state")
    async def _cmd_widgets_state(self, a: dict) -> list[dict]:
        return self.widgets.state()

    @host_command("plugin_overlay_screen")
    async def _cmd_overlay_screen(self, a: dict) -> None:
        self.widgets.screen = {"width": max(320, int(a.get("width") or 1920)),
                               "height": max(240, int(a.get("height") or 1080))}

    @host_command("plugin_widget_moved")
    async def _cmd_widget_moved(self, a: dict) -> None:
        await self.widgets.moved(str(a.get("label")), int(a.get("x") or 0), int(a.get("y") or 0))

    # ------------------------------------------------------------ Fenster eines Plugins
    @plugin_command("plugin_hello")
    async def _cmd_hello(self, plugin: str, a: dict, window: str | None) -> dict:
        if a.get("fresh"):  # Ein frisch startendes Plugin kennt alte Widgets nicht und schlösse sie nie
            await self.widgets.drop(plugin)
        return self._hello(plugin)

    async def _show_window(self, plugin: str, visible: bool) -> None:
        self._remember_window(plugin, "shown" if visible else "hidden")
        await self._overlay({"action": "show" if visible else "hide", "id": plugin})
        await self.emit("plugin-event", {"plugin": plugin, "event": "visible", "data": visible})

    @plugin_command("plugin_window", permission="window")
    async def _cmd_window(self, plugin: str, a: dict, window: str | None) -> None:
        await self._show_window(plugin, bool(a.get("visible")))

    @plugin_command("plugin_close")
    async def _cmd_close(self, plugin: str, a: dict, window: str | None) -> None:
        await self._show_window(plugin, False)

    @plugin_command("plugin_window_fit", permission="window")
    async def _cmd_window_fit(self, plugin: str, a: dict, window: str | None) -> None:
        height = a.get("height")
        await self._overlay({"action": "fit", "id": plugin,
                             "height": max(MIN_PANEL_HEIGHT, float(height)) if isinstance(height, (int, float)) else None})

    # ------------------------------------------------------------ Speicher, Feeds, FPS
    @plugin_command("plugin_storage_get", permission="storage")
    async def _cmd_storage_get(self, plugin: str, a: dict, window: str | None) -> str | None:
        try:
            return self._data_file(plugin, str(a.get("key"))).read_text(encoding="utf-8")
        except FileNotFoundError:
            return None

    @plugin_command("plugin_storage_set", permission="storage")
    async def _cmd_storage_set(self, plugin: str, a: dict, window: str | None) -> None:
        self._storage_set(plugin, str(a.get("key")), str(a.get("value")))

    @plugin_command("plugin_boss_timers", permission="feed:boss-timers")
    async def _cmd_boss_timers(self, plugin: str, a: dict, window: str | None) -> Any:
        return await self.feeds.get("boss-timers", int(a.get("server") or 0))

    @plugin_command("plugin_abyss_siege", permission="feed:boss-timers")
    async def _cmd_abyss_siege(self, plugin: str, a: dict, window: str | None) -> Any:
        return await self.feeds.get("abyss-artifacts", int(a.get("server") or 0))

    @plugin_command("plugin_boss_follow", permission="feed:boss-timers")
    async def _cmd_boss_follow(self, plugin: str, a: dict, window: str | None) -> None:
        await self.feeds.follow(plugin, int(a.get("server") or 0), list(a.get("bosses") or []))

    @plugin_command("plugin_fps_watch", permission="fps")
    async def _cmd_fps_watch(self, plugin: str, a: dict, window: str | None) -> dict:
        return {"fps": None, "state": "unsupported"}  # Die Zählung gibt es nur im Windows-Meter

    @plugin_command("plugin_fps_admin", permission="fps")
    async def _cmd_fps_admin(self, plugin: str, a: dict, window: str | None) -> bool:
        return False

    # ------------------------------------------------------------ Widgets
    @plugin_command("plugin_widget_open", permission="widgets")
    async def _cmd_widget_open(self, plugin: str, a: dict, window: str | None) -> None:
        if plugin in self.disabled():
            raise PluginError("Dieses Plugin ist ausgeschaltet")
        await self.widgets.open(plugin, a)

    @plugin_command("plugin_widget_close", permission="widgets")
    async def _cmd_widget_close(self, plugin: str, a: dict, window: str | None) -> None:
        await self.widgets.close(plugin, a.get("name"))

    @plugin_command("plugin_widget_send", permission="widgets")
    async def _cmd_widget_send(self, plugin: str, a: dict, window: str | None) -> None:
        await self.emit("plugin-event", {"plugin": plugin, "event": "widget", "data": _message(a),
                                         "__window": f"widget:{plugin}:{a.get('name')}"})

    @plugin_command("plugin_widgets_lock", permission="widgets")
    async def _cmd_widgets_lock(self, plugin: str, a: dict, window: str | None) -> None:
        await self.widgets.lock(plugin, bool(a.get("locked")))

    @plugin_command("plugin_widgets_locked", permission="widgets")
    async def _cmd_widgets_locked(self, plugin: str, a: dict, window: str | None) -> bool:
        return self.widgets.locked(plugin)

    @plugin_command("plugin_widget_where", permission="widgets")
    async def _cmd_widget_where(self, plugin: str, a: dict, window: str | None) -> dict | None:
        return self.widgets.where(plugin, a.get("name"))

    @plugin_command("plugin_widget_place", permission="widgets")
    async def _cmd_widget_place(self, plugin: str, a: dict, window: str | None) -> None:
        await self.widgets.place(plugin, a.get("name"), int(a.get("x") or 0), int(a.get("y") or 0))

    # ------------------------------------------------------------ aus einem Widget-Fenster
    @plugin_command("plugin_widget_hello")
    async def _cmd_widget_hello(self, plugin: str, a: dict, window: str | None) -> dict:
        return {"plugin": plugin, "name": _widget_name(window), "locked": self.widgets.locked(plugin),
                "language": self.language()}

    @plugin_command("plugin_widget_post")
    async def _cmd_widget_post(self, plugin: str, a: dict, window: str | None) -> None:
        name = _widget_name(window)
        await self.emit("plugin-event", {"plugin": plugin, "event": "widget-message",
                                         "data": {"name": name, "data": _message(a)}})

    @plugin_command("plugin_widget_area")
    async def _cmd_widget_area(self, plugin: str, a: dict, window: str | None) -> None:
        await self.widgets.set_areas(window or "", a.get("rects"))
