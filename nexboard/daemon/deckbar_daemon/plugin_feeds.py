"""Boss-Daten von A2Tools für Plugins: Feed-Dateien und, solange ein Plugin Bosse verfolgt, eine Live-Verbindung je Server."""
from __future__ import annotations

import asyncio
import json
import logging
import time
from collections.abc import Awaitable, Callable
from typing import Any

import aiohttp

from .plugin_files import PluginError

log = logging.getLogger(__name__)

FEED_URL = "https://cdn.a2tools.app/feeds"
LIVE_URL = "wss://a2tools.app/api/boss-timers/live"
FEED_CACHE = 2.0
MAX_FOLLOW = 50


class BossFeeds:
    def __init__(self, session: Callable[[], Awaitable[aiohttp.ClientSession]],
                 tell: Callable[[str, Any], Awaitable[None]]) -> None:
        self.session = session
        self.tell = tell  # Ereignis an alle Plugins mit dem Recht feed:boss-timers
        self._feeds: dict[tuple[str, int], tuple[float, Any]] = {}
        self._follows: dict[tuple[str, int], set[str]] = {}
        self._live: dict[int, asyncio.Task] = {}
        self._live_wanted: dict[int, asyncio.Event] = {}

    async def stop(self) -> None:
        tasks = list(self._live.values())
        for task in tasks:
            task.cancel()
        await asyncio.gather(*tasks, return_exceptions=True)
        self._live = {}

    async def get(self, feed: str, server: int) -> Any:
        if not 1000 <= server < 10000:
            raise PluginError("keine Server-Kennung")
        key = (feed, server)
        now = time.monotonic()
        cached = self._feeds.get(key)
        if cached and now - cached[0] < FEED_CACHE:
            return cached[1]
        http = await self.session()
        try:
            async with http.get(f"{FEED_URL}/{feed}/{server}.json", timeout=aiohttp.ClientTimeout(total=15)) as r:
                if r.status == 404:
                    value = None
                elif r.status == 200:
                    value = json.loads(await r.read())
                else:
                    raise PluginError(f"Der Feed antwortete {r.status}")
        except (aiohttp.ClientError, TimeoutError, ValueError) as e:
            raise PluginError(str(e)) from e
        self._feeds[key] = (now, value)
        return value

    def _wanted(self, server: int) -> list[str]:
        return sorted({b for (_, s), bosses in self._follows.items() if s == server for b in bosses})

    async def follow(self, plugin: str, server: int, bosses: list) -> None:
        if not 1000 <= server < 10000:
            raise PluginError("keine Server-Kennung")
        clean = {str(b) for b in bosses if isinstance(b, (str, int)) and str(b).isdigit() and len(str(b)) <= 16}
        clean = set(sorted(clean)[:MAX_FOLLOW])
        if clean:
            self._follows[(plugin, server)] = clean
        else:
            self._follows.pop((plugin, server), None)
        self._apply_follows(server)

    def _apply_follows(self, server: int) -> None:
        if self._wanted(server):
            task = self._live.get(server)
            if task is None or task.done():
                self._live_wanted[server] = asyncio.Event()
                self._live[server] = asyncio.create_task(self._live_run(server))
            else:
                self._live_wanted[server].set()
        elif server in self._live:
            self._live.pop(server).cancel()
            self._live_wanted.pop(server, None)

    async def forget(self, plugin: str) -> None:
        servers = [s for p, s in self._follows if p == plugin]
        for server in servers:
            self._follows.pop((plugin, server), None)
            self._apply_follows(server)

    async def _live_run(self, server: int) -> None:
        """Eine Verbindung je Server, solange etwas verfolgt wird, sonst nur die Feed-Datei."""
        backoff = 2.0
        changed = self._live_wanted[server]
        while self._wanted(server):
            try:
                http = await self.session()
                async with http.ws_connect(f"{LIVE_URL}?server={server}", timeout=aiohttp.ClientWSTimeout(ws_close=15),
                                           max_msg_size=1 << 20) as ws:
                    backoff = 2.0
                    follow = self._wanted(server)
                    await ws.send_str(json.dumps({"op": "follow", "bosses": follow}))
                    await self.tell("bossLive", {"type": "status", "server": server, "connected": True})
                    last_ping = time.monotonic()
                    heard = last_ping
                    while True:
                        if changed.is_set():
                            changed.clear()
                            if self._wanted(server) != follow:
                                follow = self._wanted(server)
                                await ws.send_str(json.dumps({"op": "follow", "bosses": follow}))
                        if time.monotonic() - last_ping >= 30:
                            await ws.send_str("ping")
                            last_ping = time.monotonic()
                        if time.monotonic() - heard >= 75:
                            break  # zwei Pings ohne Antwort: Verbindung tot
                        try:
                            msg = await ws.receive(timeout=5)
                        except TimeoutError:
                            continue
                        if msg.type == aiohttp.WSMsgType.TEXT:
                            heard = time.monotonic()
                            if msg.data == "pong":
                                continue
                            data = json.loads(msg.data)
                            if isinstance(data, dict):
                                await self.tell("bossLive", {**data, "server": server})
                        elif msg.type in (aiohttp.WSMsgType.CLOSE, aiohttp.WSMsgType.CLOSED, aiohttp.WSMsgType.ERROR):
                            if ws.close_code == 4004:
                                return  # Diesen Server führt die Seite nicht
                            break
            except asyncio.CancelledError:
                raise
            except (aiohttp.ClientError, TimeoutError, ValueError, OSError) as e:
                log.debug("Boss live %s: %s", server, e)
            await self.tell("bossLive", {"type": "status", "server": server, "connected": False})
            await asyncio.sleep(backoff)
            backoff = min(backoff * 2, 60.0)
