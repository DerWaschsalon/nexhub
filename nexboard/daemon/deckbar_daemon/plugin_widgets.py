"""Widgets der Plugins auf der Overlay-Fläche: Stand, Platz, Sperre und die Meldung an Seiten und Overlay."""
from __future__ import annotations

import re
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from typing import Any

from .plugin_files import PluginError

MAX_WIDGETS = 16
MAX_AREAS = 64
WIDGET_NAME = re.compile(r"[a-z0-9-]{1,32}")
SAVED_PLACE = re.compile(r"(-?\d+),(-?\d+)")


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


def _size(value: Any) -> float:
    value = float(value) if isinstance(value, (int, float)) else 64.0
    return max(24.0, min(value, 800.0))


class PluginWidgets:
    def __init__(self, settings: Callable[[], dict], save_setting: Callable[[str, str], Any],
                 emit: Callable[[str, Any], Awaitable[None]]) -> None:
        self.settings = settings
        self.save_setting = save_setting
        self.emit = emit
        # Stand für die Overlay-Seite (ihre eine Ereignisverbindung)
        self.listener: Callable[[list[dict]], Awaitable[None]] | None = None
        self.items: dict[str, WidgetState] = {}
        self.screen = {"width": 1920, "height": 1080}

    # ------------------------------------------------------------ Stand
    def state(self) -> list[dict]:
        return [{"label": w.label, "plugin": w.plugin, "name": w.name, "width": w.width, "height": w.height,
                 "x": w.x, "y": w.y, "open": w.open, "areas": w.areas, "locked": self.locked(w.plugin)}
                for w in self.items.values()]

    async def publish(self) -> None:
        await self.emit("plugin-widgets", self.state())
        if self.listener:
            await self.listener(self.state())

    def get(self, plugin: str, name: Any) -> WidgetState | None:
        return self.items.get(f"widget:{plugin}:{name}")

    async def drop(self, plugin: str) -> None:
        gone = [k for k, w in self.items.items() if w.plugin == plugin]
        for key in gone:
            del self.items[key]
        if gone:
            await self.publish()

    # ------------------------------------------------------------ Sperre
    def _locked_key(self, plugin: str) -> str:
        return f"dpsMeter.pluginWidgetsLocked.{plugin}"

    def locked(self, plugin: str) -> bool:
        return self.settings().get(self._locked_key(plugin)) == "true"

    async def lock(self, plugin: str, locked: bool) -> None:
        self.save_setting(self._locked_key(plugin), "true" if locked else "false")
        await self.emit("plugin-event", {"plugin": plugin, "event": "locked", "data": locked})
        await self.publish()

    # ------------------------------------------------------------ Platz
    def _place_key(self, plugin: str, name: str) -> str:
        return f"dpsMeter.pluginWidget.{plugin}.{name}"

    def _on_screen(self, x: int, y: int, width: float, height: float) -> tuple[int, int]:
        return (max(0, min(x, int(self.screen["width"] - min(width, self.screen["width"])))),
                max(0, min(y, int(self.screen["height"] - min(height, self.screen["height"])))))

    def _first_place(self, plugin: str, name: str, width: float, height: float) -> tuple[int, int]:
        """Wo es zuletzt lag, sonst neben den anderen des Plugins, sonst ein freier Platz am rechten Rand."""
        m = SAVED_PLACE.fullmatch(self.settings().get(self._place_key(plugin, name), ""))
        if m:
            return self._on_screen(int(m[1]), int(m[2]), width, height)
        others = [w for w in self.items.values() if w.plugin == plugin]
        if others:
            last = others[-1]
            return self._on_screen(int(last.x + last.width + 4), last.y, width, height)
        taken = len({w.plugin for w in self.items.values()})
        return self._on_screen(int(self.screen["width"] - width - 40), 160 + 90 * taken, width, height)

    @staticmethod
    def _checked_name(name: Any) -> str:
        name = str(name)
        if not WIDGET_NAME.fullmatch(name):
            raise PluginError("Ein Widget-Name hat 1 bis 32 Kleinbuchstaben, Ziffern oder '-'")
        return name

    async def open(self, plugin: str, a: dict) -> None:
        name = self._checked_name(a.get("name"))
        width, height = _size(a.get("width")), _size(a.get("height"))
        w = self.get(plugin, name)
        if w:
            w.width, w.height, w.open = width, height, True
            w.x, w.y = self._on_screen(w.x, w.y, width, height)
        else:
            mine = [k for k, x in self.items.items() if x.plugin == plugin]
            if len(mine) >= MAX_WIDGETS:
                spare = next((k for k in mine if not self.items[k].open), None)
                if spare is None:
                    raise PluginError(f"höchstens {MAX_WIDGETS} Widgets")
                del self.items[spare]
            x, y = self._first_place(plugin, name, width, height)
            self.items[f"widget:{plugin}:{name}"] = WidgetState(plugin, name, width, height, x, y)
        await self.publish()

    async def close(self, plugin: str, name: Any) -> None:
        if w := self.get(plugin, name):
            w.open = False
            await self.publish()

    def where(self, plugin: str, name: Any) -> dict | None:
        w = self.get(plugin, name)
        if w is None:
            return None
        return {"x": w.x, "y": w.y, "width": int(w.width), "height": int(w.height),
                "screen": {"x": 0, "y": 0, **self.screen}}

    async def place(self, plugin: str, name: Any, x: int, y: int) -> None:
        """Ein Plugin setzt den Platz eines Widgets; er gilt auch, wenn es noch nicht offen ist."""
        name = self._checked_name(name)
        w = self.get(plugin, name)
        x, y = self._on_screen(x, y, w.width if w else 64, w.height if w else 64)
        self.save_setting(self._place_key(plugin, name), f"{x},{y}")
        if w:
            w.x, w.y = x, y
            await self.publish()

    async def moved(self, label: str, x: int, y: int) -> None:
        """Die Overlay-Seite meldet, wohin ein Widget gezogen wurde."""
        w = self.items.get(label)
        if w is None:
            return
        w.x, w.y = self._on_screen(x, y, w.width, w.height)
        self.save_setting(self._place_key(w.plugin, w.name), f"{w.x},{w.y}")
        await self.emit("plugin-event", {"plugin": w.plugin, "event": "widget-moved",
                                         "data": {"name": w.name, "x": w.x, "y": w.y}})
        await self.publish()

    async def set_areas(self, label: str, rects: Any) -> None:
        """Klickbereiche eines Widgets, gemeldet aus seinem Fenster."""
        w = self.items.get(label)
        if w is None:
            raise PluginError("kein Widget-Fenster")
        if not isinstance(rects, list) or len(rects) > MAX_AREAS:
            raise PluginError("keine Fläche")
        w.areas = [[float(r["x"]), float(r["y"]), float(r["width"]), float(r["height"])] for r in rects]
        await self.publish()
