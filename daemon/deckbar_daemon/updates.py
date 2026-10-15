"""Nach Updates suchen: neue Commits der NexBoard und neue Releases des A2Tools DPS Meter.

Einmal kurz nach dem Start und dann täglich (oder per POST /api/updates/check):
  - NexBoard: `git fetch` im Repo, Commits auf dem Upstream-Zweig, die lokal fehlen
  - A2Tools: neuestes Release laut GitHub-API gegen das Tag im Submodul capture/a2tools
    (Spiel-Patches ändern Opcodes und Datentabellen, das Meter zieht schnell nach)

Installiert wird mit update.sh im Repo. run() öffnet dafür ein Konsole-Fenster: Baut update.sh
deckbar-capture neu, fragt sudo dort nach dem Passwort für cap_net_raw (aus einem Dienst heraus
gibt es keinen Passwort-Dialog). Das Fenster läuft als eigene systemd-Unit und überlebt so den
Neustart von Daemon und Overlay. Ergebnis zusätzlich per Desktop-Benachrichtigung.
"""
from __future__ import annotations

import asyncio
import json
import logging
import re
import shutil
import time
from pathlib import Path
from typing import Any, Awaitable, Callable

import aiohttp

log = logging.getLogger(__name__)

REPO = Path(__file__).resolve().parents[2]
A2_RELEASES = "https://api.github.com/repos/taengu/A2Tools-DPS-Meter/releases/latest"
FIRST_CHECK_S = 120
CHECK_EVERY_S = 24 * 3600
UNIT = "deckbar-update"


def version_tuple(tag: str | None) -> tuple[int, ...]:
    """"v2.0.62" → (2, 0, 62); Unlesbares → ()."""
    m = re.match(r"v?(\d+(?:\.\d+)*)", (tag or "").strip())
    return tuple(int(x) for x in m.group(1).split(".")) if m else ()


async def _git(*args: str, cwd: Path) -> tuple[int, str]:
    proc = await asyncio.create_subprocess_exec(
        "git", "-C", str(cwd), *args, stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE)
    out, err = await proc.communicate()
    return proc.returncode or 0, (out or err).decode(errors="replace").strip()


class Updates:
    def __init__(self, repo: Path = REPO) -> None:
        self.repo = repo
        self.state: dict[str, Any] = {"checked_at": None, "error": "", "running": False,
                                      "deckbar": None, "a2tools": None, "available": False}
        self.listeners: list[Callable[[], Awaitable[None]]] = []
        self._wake = asyncio.Event()

    def info(self) -> dict:
        return dict(self.state)

    async def _changed(self) -> None:
        for fn in self.listeners:
            await fn()

    async def watch(self) -> None:
        await self._sleep(FIRST_CHECK_S)
        while True:
            await self.check()
            await self._sleep(CHECK_EVERY_S)

    async def _sleep(self, seconds: float) -> None:
        self._wake.clear()
        try:
            await asyncio.wait_for(self._wake.wait(), seconds)
        except TimeoutError:
            pass

    def check_now(self) -> None:
        self._wake.set()

    # ------------------------------------------------------------ Prüfen
    async def check(self) -> None:
        errors = []
        try:
            self.state["deckbar"] = await self._check_repo()
        except (OSError, RuntimeError) as e:
            errors.append(f"NexBoard: {e}")
        try:
            self.state["a2tools"] = await self._check_a2tools()
        except (OSError, RuntimeError, aiohttp.ClientError, TimeoutError, ValueError) as e:
            errors.append(f"A2Tools: {e}")
        d, a = self.state["deckbar"] or {}, self.state["a2tools"] or {}
        self.state.update(checked_at=int(time.time()), error="; ".join(errors),
                          available=bool(d.get("behind")) or bool(a.get("newer")))
        if self.state["available"]:
            log.info("Update verfügbar: NexBoard %s Commit(s), A2Tools %s → %s",
                     d.get("behind", 0), a.get("current"), a.get("latest"))
        await self._changed()

    async def _check_repo(self) -> dict:
        r = self.repo
        code, out = await _git("fetch", "--quiet", cwd=r)
        if code:
            raise RuntimeError(f"git fetch: {out[:200]}")
        code, upstream = await _git("rev-parse", "--abbrev-ref", "@{upstream}", cwd=r)
        if code:
            # lokaler Entwicklungszweig: nichts zu holen, kein Fehler
            _, branch = await _git("rev-parse", "--abbrev-ref", "HEAD", cwd=r)
            return {"upstream": None, "branch": branch, "behind": 0, "ahead": 0, "latest": ""}
        _, behind = await _git("rev-list", "--count", "HEAD..@{upstream}", cwd=r)
        _, ahead = await _git("rev-list", "--count", "@{upstream}..HEAD", cwd=r)
        _, subject = await _git("log", "-1", "--format=%s", "@{upstream}", cwd=r)
        return {"upstream": upstream, "behind": int(behind or 0), "ahead": int(ahead or 0), "latest": subject}

    async def _check_a2tools(self) -> dict:
        sub = self.repo / "capture" / "a2tools"
        code, current = await _git("describe", "--tags", "--abbrev=0", cwd=sub)
        if code:
            raise RuntimeError("Submodul capture/a2tools fehlt (capture/build.sh)")
        timeout = aiohttp.ClientTimeout(total=15)
        async with aiohttp.ClientSession(timeout=timeout) as s:
            async with s.get(A2_RELEASES, headers={"Accept": "application/vnd.github+json"}) as r:
                if r.status != 200:
                    raise RuntimeError(f"GitHub antwortet {r.status}")
                rel = json.loads(await r.text())
        latest = str(rel.get("tag_name") or "")
        return {"current": current, "latest": latest, "url": rel.get("html_url"),
                "newer": version_tuple(latest) > version_tuple(current)}

    # ------------------------------------------------------------ Installieren
    async def run(self) -> str:
        """update.sh als eigene User-Unit starten (überlebt den Neustart des Daemons)."""
        if self.state["running"]:
            return "läuft schon"
        args = [str(self.repo / "update.sh"), "--notify"]
        if (self.state.get("a2tools") or {}).get("newer"):
            args.append("--a2tools")
        if not shutil.which("systemd-run"):
            raise RuntimeError("systemd-run fehlt")
        if shutil.which("konsole"):
            args = ["konsole", "--hold", "-p", "tabtitle=NexBoard-Update", "-e", *args]
        proc = await asyncio.create_subprocess_exec(
            "systemd-run", "--user", "--collect", f"--unit={UNIT}-{int(time.time())}",
            "--property=Type=exec", *args,
            stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.STDOUT)
        out, _ = await proc.communicate()
        if proc.returncode:
            raise RuntimeError(out.decode(errors="replace").strip()[:300])
        self.state["running"] = True
        # update.sh startet den Daemon neu; klappt es nicht, nach 15 min wieder anbieten
        asyncio.get_running_loop().call_later(900, self.state.__setitem__, "running", False)
        await self._changed()
        log.info("Update gestartet: %s", " ".join(args))
        return "gestartet"
