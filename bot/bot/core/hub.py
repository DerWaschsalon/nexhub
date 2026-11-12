"""Abfragen an die Hub-API im internen Docker-Netz (`HUB_INTERNAL_URL`, z. B. http://api:8000).

Der Bot meldet sich mit demselben Schlüssel an wie der Hub bei der Steuer-API (`BOT_CONTROL_KEY`).
Die Pfade unter /api/internal/… sperrt Caddy nach außen, sie sind nur im Docker-Netz erreichbar.
"""

from __future__ import annotations

import asyncio
import logging
import os
from typing import Any

import aiohttp

from ..errors import UserError
from .web import control_key

log = logging.getLogger(__name__)

TIMEOUT_S = 10
NOT_REACHABLE = "NexHub nicht erreichbar"


class HubClient:
    def __init__(self, base_url: str, key: str) -> None:
        self.base_url = base_url.rstrip("/")
        self.key = key
        self._session: aiohttp.ClientSession | None = None

    @classmethod
    def from_env(cls) -> HubClient | None:
        """Ohne Adresse oder Schlüssel gibt es keine Verbindung zum Hub."""
        url = os.getenv("HUB_INTERNAL_URL", "").strip()
        key = control_key()
        if not url or not key:
            return None
        return cls(url, key)

    def _s(self) -> aiohttp.ClientSession:
        # Erst beim ersten Abruf anlegen: eine ClientSession braucht eine laufende Event-Loop
        if self._session is None or self._session.closed:
            self._session = aiohttp.ClientSession(
                timeout=aiohttp.ClientTimeout(total=TIMEOUT_S), headers={"Authorization": f"Bearer {self.key}"})
        return self._session

    async def get(self, path: str, params: dict[str, str]) -> Any | None:
        """JSON-Antwort des Hubs; 404 heißt „nichts gefunden“ (None), alles andere Unerwartete UserError."""
        try:
            async with self._s().get(self.base_url + path, params=params) as resp:
                if resp.status == 404:
                    return None
                resp.raise_for_status()
                return await resp.json()
        except (aiohttp.ClientError, asyncio.TimeoutError) as e:
            log.warning("Hub-Abfrage %s: %r", path, e)
            raise UserError(NOT_REACHABLE) from e

    async def close(self) -> None:
        if self._session is not None and not self._session.closed:
            await self._session.close()
