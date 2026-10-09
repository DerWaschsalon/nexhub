"""PipeWire-Lautstärke/Mute über wpctl, Änderungen ereignisbasiert über `pactl subscribe`."""
from __future__ import annotations

import asyncio
import logging
import re

from .proc import have, run
from .state import State

log = logging.getLogger(__name__)

NODES = {"sink": "@DEFAULT_AUDIO_SINK@", "source": "@DEFAULT_AUDIO_SOURCE@"}
PREFIX = {"sink": "out", "source": "mic"}
_VOL_RE = re.compile(r"Volume:\s*([0-9.]+)(\s*\[MUTED\])?")
# pactl-Ereignisse, nach denen sich Standardgerät oder Pegel geändert haben kann
_EVENT_RE = re.compile(r"Event '(change|new|remove)' on (sink|source|server)\b")


def parse_volume(text: str) -> tuple[int, bool] | None:
    m = _VOL_RE.search(text)
    if not m:
        return None
    return round(float(m.group(1)) * 100), bool(m.group(2))


class Audio:
    def __init__(self, state: State) -> None:
        self.state = state
        self._refresh_pending = False
        self._setters: dict[str, asyncio.Task] = {}
        self._pending_value: dict[str, tuple[int, int]] = {}

    # ---------------------------------------------------------------- lesen
    async def refresh(self) -> None:
        values = {}
        for target, node in NODES.items():
            rc, out, err = await run("wpctl", "get-volume", node)
            parsed = parse_volume(out) if rc == 0 else None
            if parsed is None:
                log.debug("wpctl get-volume %s fehlgeschlagen: %s", node, err.strip())
                continue
            vol, muted = parsed
            values[f"{PREFIX[target]}_volume"] = vol
            values[f"{PREFIX[target]}_muted"] = muted
        if values:
            self.state.update(**values)

    def _schedule_refresh(self) -> None:
        # mehrere Ereignisse kurz hintereinander zu einem wpctl-Aufruf bündeln
        if self._refresh_pending:
            return
        self._refresh_pending = True

        async def later():
            await asyncio.sleep(0.03)
            self._refresh_pending = False
            await self.refresh()

        asyncio.ensure_future(later())

    async def watch(self) -> None:
        if not have("wpctl"):
            log.error("wpctl nicht gefunden – Audio-Status nicht verfügbar")
            return
        await self.refresh()
        if not have("pactl"):
            log.warning("pactl nicht gefunden – Audio-Status wird alle 2 s abgefragt")
            while True:
                await asyncio.sleep(2)
                await self.refresh()
        while True:
            proc = await asyncio.create_subprocess_exec(
                "pactl", "subscribe", stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.DEVNULL
            )
            log.info("pactl subscribe läuft (pid %s)", proc.pid)
            assert proc.stdout
            try:
                async for raw in proc.stdout:
                    if _EVENT_RE.search(raw.decode(errors="replace")):
                        self._schedule_refresh()
            finally:
                if proc.returncode is None:
                    proc.kill()
                await proc.wait()
            log.warning("pactl subscribe beendet (rc=%s), Neustart in 2 s", proc.returncode)
            await asyncio.sleep(2)
            await self.refresh()

    # ---------------------------------------------------------------- schreiben
    async def toggle_mute(self, target: str) -> None:
        await self._wpctl("set-mute", NODES[target], "toggle")

    async def set_mute(self, target: str, muted: bool) -> None:
        await self._wpctl("set-mute", NODES[target], "1" if muted else "0")

    async def step(self, target: str, step: int, limit: int) -> None:
        sign = "+" if step >= 0 else "-"
        await self._wpctl("set-volume", "-l", f"{limit / 100:.2f}", NODES[target], f"{abs(step)}%{sign}")

    def set_volume(self, target: str, value: int, limit: int) -> None:
        """Setzt die Lautstärke. Kommen Slider-Werte schneller als wpctl, gewinnt der letzte."""
        self._pending_value[target] = (value, limit)
        task = self._setters.get(target)
        if task is None or task.done():
            self._setters[target] = asyncio.ensure_future(self._drain(target))

    async def _drain(self, target: str) -> None:
        while target in self._pending_value:
            value, limit = self._pending_value.pop(target)
            value = max(0, min(value, limit))
            await self._wpctl("set-volume", NODES[target], f"{value / 100:.2f}")

    async def _wpctl(self, *args: str) -> None:
        rc, _, err = await run("wpctl", *args)
        if rc != 0:
            log.warning("wpctl %s: %s", " ".join(args), err.strip())
        # pactl subscribe meldet die Änderung ohnehin; ohne pactl selbst nachlesen
        if not have("pactl"):
            await self.refresh()
