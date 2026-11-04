"""Zentraler Status (Lautstärke, Mute, Track …) mit Diff-Benachrichtigung."""
from __future__ import annotations

import asyncio
from typing import Any, Awaitable, Callable

Listener = Callable[[dict[str, Any]], Awaitable[None] | None]


class State:
    def __init__(self) -> None:
        self._values: dict[str, Any] = {
            "out_volume": 0,
            "out_muted": False,
            "mic_volume": 0,
            "mic_muted": False,
            "playing": False,
            "track": None,
            "art_url": None,  # Cover des aktuellen Titels (das Gerät bekommt das Bild per `art`)
            "dps": None,  # AION 2, siehe dps.py
            "dps_active": False,
            "claude": None,  # Claude-Nutzung, siehe claude.py
        }
        self._listeners: list[Listener] = []

    @property
    def values(self) -> dict[str, Any]:
        return dict(self._values)

    def subscribe(self, fn: Listener) -> None:
        self._listeners.append(fn)

    def update(self, **values: Any) -> dict[str, Any]:
        """Übernimmt Werte und benachrichtigt nur über tatsächliche Änderungen."""
        diff = {k: v for k, v in values.items() if self._values.get(k, object()) != v}
        if not diff:
            return diff
        self._values.update(diff)
        for fn in self._listeners:
            res = fn(diff)
            if asyncio.iscoroutine(res):
                asyncio.ensure_future(res)
        return diff
