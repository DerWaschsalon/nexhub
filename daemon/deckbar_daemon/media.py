"""MPRIS über playerctl: Steuerung und Trackinfo per `playerctl --follow`."""
from __future__ import annotations

import asyncio
import logging

from .proc import have, run
from .state import State

log = logging.getLogger(__name__)

SEP = "\x1f"  # Unit Separator: kommt in Titeln praktisch nie vor
FORMAT = SEP.join(["{{status}}", "{{artist}}", "{{title}}", "{{playerName}}", "{{mpris:artUrl}}"])
OPS = {
    "play_pause": "play-pause",
    "play": "play",
    "pause": "pause",
    "stop": "stop",
    "next": "next",
    "previous": "previous",
}


def parse_line(line: str) -> dict:
    line = line.rstrip("\n")
    parts = line.split(SEP)
    if len(parts) < 4 or not parts[0]:
        # leere Zeile = kein Player mehr vorhanden
        return {"playing": False, "track": None, "art_url": None}
    status, artist, title, player = parts[:4]
    art_url = parts[4] if len(parts) > 4 and parts[4] else None
    if not title and not artist:
        return {"playing": status == "Playing", "track": None, "art_url": None}
    return {
        "playing": status == "Playing",
        "track": {"title": title, "artist": artist, "player": player},
        "art_url": art_url,
    }


class Media:
    def __init__(self, state: State, player: str | None = None) -> None:
        self.state = state
        self.player = player

    def _base(self, player: str | None = None) -> list[str]:
        p = player or self.player
        return ["playerctl", "-p", p] if p else ["playerctl"]

    async def command(self, op: str, player: str | None = None) -> None:
        if not have("playerctl"):
            log.warning("playerctl nicht installiert – Media-Aktion '%s' ignoriert", op)
            return
        rc, _, err = await run(*self._base(player), OPS[op])
        if rc != 0:
            log.info("playerctl %s: %s", OPS[op], err.strip() or f"rc={rc}")

    async def watch(self) -> None:
        warned = False
        while True:
            if not have("playerctl"):
                if not warned:
                    log.warning("playerctl nicht installiert – Trackinfo nicht verfügbar (prüfe alle 30 s)")
                    warned = True
                await asyncio.sleep(30)
                continue
            proc = await asyncio.create_subprocess_exec(
                *self._base(), "--follow", "metadata", "--format", FORMAT,
                stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.DEVNULL,
            )
            log.info("playerctl --follow läuft (pid %s)", proc.pid)
            assert proc.stdout
            try:
                async for raw in proc.stdout:
                    self.state.update(**parse_line(raw.decode(errors="replace")))
            finally:
                if proc.returncode is None:
                    proc.kill()
                await proc.wait()
            log.warning("playerctl --follow beendet (rc=%s), Neustart in 2 s", proc.returncode)
            self.state.update(playing=False, track=None, art_url=None)
            await asyncio.sleep(2)
