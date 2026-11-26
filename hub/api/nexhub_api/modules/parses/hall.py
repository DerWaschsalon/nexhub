"""Verzeichnis aller EU-Parses der Gilde für die Startseite (GET /api/parses/top und /hall). Über alle Runs zu
rechnen dauert Sekunden, deshalb hier im Hintergrund alle EVERY_SECONDS; die Routen filtern nur noch
`state.parses_index`."""
from __future__ import annotations

import asyncio
import logging
import time
from datetime import UTC, datetime
from types import SimpleNamespace

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker
from starlette.datastructures import State

from ..logs.models import Run
from .routes import ParseIndex, member_parses

log = logging.getLogger(__name__)

EVERY_SECONDS = 300


class HallOfFame:
    def __init__(self, state: State, sessionmaker: async_sessionmaker[AsyncSession]) -> None:
        self.state, self.sessionmaker = state, sessionmaker

    async def run(self) -> None:
        """Läuft, bis der Hub beendet wird."""
        while True:
            started = time.monotonic()
            try:
                await self.tick()
            except Exception:  # ein Fehler hält das Verzeichnis nicht für immer an, das alte bleibt stehen
                log.exception("Parses: Verzeichnis nicht gerechnet")
            await asyncio.sleep(max(0.0, EVERY_SECONDS - (time.monotonic() - started)))

    async def tick(self) -> ParseIndex:
        async with self.sessionmaker() as db:
            runs = (await db.scalars(select(Run).order_by(Run.start_ms))).all()
            request = SimpleNamespace(app=SimpleNamespace(state=self.state))
            entries = await member_parses(request, db, runs)  # type: ignore[arg-type]
        self.state.parses_index = ParseIndex(computed_at=datetime.now(UTC), entries=entries)
        return self.state.parses_index
