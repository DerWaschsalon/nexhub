"""Führt die Aktionen aus, die im Layout an Items hängen."""
from __future__ import annotations

import asyncio
import logging
import os

from . import keys
from .audio import Audio
from .config import (
    Action, HotkeyAction, Item, MediaAction, OpenAction, ShellAction, VolumeAction,
)
from .media import Media
from .proc import have, run

log = logging.getLogger(__name__)

MEDIA_PARTS = {"prev": "previous", "toggle": "play_pause", "next": "next"}


class ActionError(Exception):
    pass


class Executor:
    def __init__(self, audio: Audio, media: Media) -> None:
        self.audio = audio
        self.media = media
        self.last_error: str | None = None

    async def on_event(self, item: Item, event: str, value: int | None = None,
                       part: str | None = None) -> None:
        try:
            if event == "slider_change":
                await self._slider(item, value)
            elif event == "long_press":
                if item.long_action:
                    await self.run(item.long_action)
                elif item.type != "slider" and item.action:
                    # ohne eigene long_action verhält sich langes Drücken wie ein Tap
                    await self.run(item.action)
            elif event == "button_press":
                if item.type == "media":
                    op = MEDIA_PARTS.get(part or "toggle", "play_pause")
                    act = item.action if (item.action and part in (None, "toggle")) else None
                    await (self.run(act) if act else self.media.command(op))
                elif item.action:
                    await self.run(item.action)
            self.last_error = None
        except ActionError as e:
            self.last_error = f"{item.id}: {e}"
            log.warning("Aktion für '%s' fehlgeschlagen: %s", item.id, e)

    async def _slider(self, item: Item, value: int | None) -> None:
        if value is None:
            raise ActionError("slider_change ohne value")
        act = item.action
        if isinstance(act, VolumeAction):
            self.audio.set_volume(act.target, value, act.limit)
        elif isinstance(act, ShellAction):
            # Wert als Umgebungsvariable, damit beliebige Slider möglich sind
            await self._shell(act.cmd, {"DECKBAR_VALUE": str(value)})
        elif act is not None:
            raise ActionError(f"Aktion '{act.do}' passt nicht zu einem Slider")

    async def run(self, act: Action) -> None:
        if isinstance(act, MediaAction):
            await self.media.command(act.op, act.player)
        elif isinstance(act, VolumeAction):
            if act.op == "toggle_mute":
                await self.audio.toggle_mute(act.target)
            elif act.op in ("mute", "unmute"):
                await self.audio.set_mute(act.target, act.op == "mute")
            elif act.op == "step":
                await self.audio.step(act.target, act.step, act.limit)
            else:
                raise ActionError("op=set braucht einen Slider")
        elif isinstance(act, OpenAction):
            await self._spawn(["xdg-open", act.url])
        elif isinstance(act, HotkeyAction):
            await self._hotkey(act.keys)
        elif isinstance(act, ShellAction):
            await self._shell(act.cmd)

    async def _hotkey(self, combo: str) -> None:
        try:
            args = keys.ydotool_args(combo)
        except ValueError as e:
            raise ActionError(str(e)) from None
        if not have("ydotool"):
            raise ActionError("ydotool nicht installiert")
        rc, _, err = await run("ydotool", "key", *args)
        if rc != 0:
            raise ActionError(f"ydotool: {err.strip() or rc} (läuft ydotoold?)")

    async def _shell(self, cmd: str, extra_env: dict[str, str] | None = None) -> None:
        env = {**os.environ, **(extra_env or {})}
        await self._spawn(["/bin/sh", "-c", cmd], env)

    async def _spawn(self, argv: list[str], env: dict | None = None) -> None:
        """Startet losgelöst (eigene Session), damit GUI-Programme den Daemon überleben."""
        try:
            proc = await asyncio.create_subprocess_exec(
                *argv, env=env, start_new_session=True,
                stdin=asyncio.subprocess.DEVNULL,
                stdout=asyncio.subprocess.DEVNULL,
                stderr=asyncio.subprocess.PIPE,
            )
        except FileNotFoundError:
            raise ActionError(f"{argv[0]} nicht gefunden") from None

        async def reap():
            _, err = await proc.communicate()
            if proc.returncode:
                log.info("%s beendet mit rc=%s: %s", argv[-1][:60], proc.returncode,
                         err.decode(errors="replace").strip()[:200])

        asyncio.ensure_future(reap())
