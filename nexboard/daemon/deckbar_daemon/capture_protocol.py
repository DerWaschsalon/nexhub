"""Das Zeilen-JSON zwischen Daemon und `deckbar-capture` (Format siehe capture/src/main.rs und out.rs):

    {"type":"hello","cap_net_raw":true,…}         einmal beim Start
    {"type":"dps","view":{"target":…,"timeMs":…,"hp":…,"rows":[…]}}   bei jeder Änderung
    {"type":"dps_data","data":{…}}                volle DpsData, solange jemand sie braucht
    {"type":"status","port":…,"ping":…,"dungeon":…}                   bei jeder Änderung
    {"type":"fights_saved","ids":[…]}             Kampf-History geschrieben
    {"type":"reply","id":…,"ok":…,"result":…}     Antwort auf einen Befehl {"id":…,"cmd":…,…}
"""
from __future__ import annotations

import asyncio
import itertools
import json
from typing import Any

MAX_LINE = 4 * 1024 * 1024  # volle DpsData mit allen Skills
# Zeile mit der vollen DpsData, genau so geschrieben von deckbar-capture (out.rs): nur den Inhalt herausschneiden
DPS_DATA_PREFIX = b'{"type":"dps_data","data":'


def parse(raw: bytes) -> tuple[str | None, Any] | None:
    """Eine Zeile → (Typ, Inhalt); None für Unlesbares. Die volle DpsData (bis 100 KB) bleibt Text und
    geht ungeparst an die Meter-Seiten weiter."""
    if raw.startswith(DPS_DATA_PREFIX):
        return "dps_data", raw[len(DPS_DATA_PREFIX):].rstrip()[:-1].decode()
    try:
        msg = json.loads(raw)
    except ValueError:
        return None
    return (msg.get("type"), msg) if isinstance(msg, dict) else None


class Requests:
    """Befehle mit laufender Nummer und ihre noch offenen Antworten."""

    def __init__(self) -> None:
        self._pending: dict[int, asyncio.Future] = {}
        self._ids = itertools.count(1)

    def new(self, cmd: str, args: dict[str, Any]) -> tuple[int, asyncio.Future, bytes]:
        rid = next(self._ids)
        self._pending[rid] = asyncio.get_running_loop().create_future()
        return rid, self._pending[rid], (json.dumps({"id": rid, "cmd": cmd, **args}) + "\n").encode()

    def reply(self, msg: dict) -> None:
        fut = self._pending.pop(msg.get("id"), None)
        if fut and not fut.done():
            if msg.get("ok"):
                fut.set_result(msg.get("result"))
            else:
                fut.set_exception(RuntimeError(str(msg.get("error"))))

    def drop(self, rid: int) -> None:
        self._pending.pop(rid, None)

    def cancel_all(self) -> None:
        for fut in self._pending.values():
            fut.cancel()
        self._pending.clear()
