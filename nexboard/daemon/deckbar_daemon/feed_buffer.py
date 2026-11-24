"""Merkt sich Ereignisse einer Art aus dem Feed des Mitschnitts (`plugin_feed`), bis ein Run sie abholt.

Der Mitschnitt meldet Würfel-Beute (`lootRoll`) und Tode (`deathRecap`) in dem Moment, in dem sie
passieren. Ein Run steht erst später fest; bis dahin liegen die Ereignisse hier, mit ihrer Zeit.
"""
from __future__ import annotations

from collections import deque
from collections.abc import Callable
from typing import Any

MAX_ROWS = 2000  # reicht für viele Stunden; die ältesten fallen zuerst weg
Pick = Callable[[dict[str, Any], int], dict[str, Any] | None]


class FeedBuffer:
    """Hört auf eine Art von Feed-Ereignis. `pick` macht aus dem Ereignis die Zeile, die gemerkt wird
    (mit `t_ms`), oder None, wenn es nicht zählt."""

    def __init__(self, event: str, pick: Pick) -> None:
        self.event, self.pick = event, pick
        self.rows: deque[dict[str, Any]] = deque(maxlen=MAX_ROWS)

    async def on_capture(self, kind: str, payload: Any) -> None:
        """Abnehmer für Capture.data_listeners."""
        if kind != "plugin_feed" or payload.get("event") != self.event:
            return
        row = self.pick(payload.get("data") or {}, int(payload.get("at") or 0))
        if row is not None:
            self.rows.append(row)

    def between(self, start_ms: int, end_ms: int) -> list[dict[str, Any]]:
        return [row for row in self.rows if start_ms <= row["t_ms"] <= end_ms]
