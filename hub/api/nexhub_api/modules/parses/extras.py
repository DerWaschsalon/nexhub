"""Weitere Daten von Abyss Logs im Hintergrund, getrennt von den Ranglisten (fetcher.py):

- Dungeons: Name, Schwierigkeit und Art je Dungeon-ID, einmal am Tag. Liegen in `state.dungeon_info`
  ({id: (Name, Schwierigkeit, Art)}); die Runs (modules/logs) zeigen sie, wo Abyss Logs die ID kennt.
- Vergleichswerte: DPS-Verteilung der letzten Woche je Boss, Klasse und Kampfkraft (Abyss Logs /statistics),
  für Bosse aus den Runs der letzten WINDOW_DAYS Tage, höchstens PER_TICK je Takt, jede einmal am Tag neu.

Geht etwas schief, bleibt der alte Stand stehen.
"""
from __future__ import annotations

import asyncio
import logging
import time
from datetime import UTC, datetime, timedelta

import httpx
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker
from starlette.datastructures import State

from ..bis import abysslogs
from ..bis.abysslogs import AbyssError
from ..logs.models import Run
from .calc import needed_pairs
from .fetcher import PAUSE_SECONDS, WINDOW_DAYS
from .models import DungeonInfo, ParseBenchmark

log = logging.getLogger(__name__)

TICK_SECONDS = 600
PER_TICK = 5
MAX_AGE = timedelta(hours=24)


def _utc(at: datetime) -> datetime:
    return at if at.tzinfo else at.replace(tzinfo=UTC)


class AbyssExtras:
    def __init__(self, state: State, sessionmaker: async_sessionmaker[AsyncSession], http: httpx.AsyncClient,
                 pause: float = PAUSE_SECONDS) -> None:
        self.state, self.sessionmaker, self.http, self.pause = state, sessionmaker, http, pause

    async def run(self) -> None:
        """Läuft, bis der Hub beendet wird."""
        await self.load()
        while True:
            started = time.monotonic()
            try:
                await self.tick()
            except Exception:  # eine kaputte Quelle hält den Abruf nicht für immer an
                log.exception("Abyss Logs: Takt abgebrochen")
            await asyncio.sleep(max(0.0, TICK_SECONDS - (time.monotonic() - started)))

    async def tick(self) -> int:
        """Ein Takt; gibt zurück, wie viele Bosse neue Vergleichswerte bekamen."""
        await self.dungeons()
        return await self.benchmarks()

    async def load(self) -> None:
        """Dungeons aus der Datenbank nach `state.dungeon_info`."""
        async with self.sessionmaker() as db:
            rows = (await db.scalars(select(DungeonInfo))).all()
        self.state.dungeon_info = {r.dungeon_id: (r.name, r.tier, r.category) for r in rows}

    async def dungeons(self) -> bool:
        """Die Dungeonliste, wenn sie älter als einen Tag ist; True, wenn sie neu geholt wurde."""
        async with self.sessionmaker() as db:
            last = await db.scalar(select(func.max(DungeonInfo.fetched_at)))
        if last is not None and datetime.now(UTC) - _utc(last) < MAX_AGE:
            return False
        try:
            rows = await abysslogs.dungeons(self.http)
        except AbyssError as e:
            log.info("Abyss Logs Dungeons: %s", e)
            return False
        now = datetime.now(UTC)
        async with self.sessionmaker() as db:
            stored = {d.dungeon_id: d for d in (await db.scalars(select(DungeonInfo))).all()}
            for r in rows:
                d = stored.get(r["id"]) or DungeonInfo(dungeon_id=r["id"])
                d.name, d.tier, d.category, d.fetched_at = r["name"][:120], r["tier"], r["category"], now
                db.add(d)
            await db.commit()
        await self.load()
        return True

    async def benchmarks(self) -> int:
        since = int(time.time() * 1000) - WINDOW_DAYS * 86_400_000
        async with self.sessionmaker() as db:
            summaries = (await db.scalars(select(Run.summary).where(Run.start_ms >= since))).all()
            stored = {b.boss: _utc(b.fetched_at) for b in (await db.scalars(select(ParseBenchmark))).all()}
        now = datetime.now(UTC)
        bosses = sorted({boss for boss, _ in needed_pairs(summaries)},
                        key=lambda b: stored.get(b, datetime.min.replace(tzinfo=UTC)))
        due = [b for b in bosses if b not in stored or now - stored[b] > MAX_AGE][:PER_TICK]
        done = 0
        for i, boss in enumerate(due):
            if i:
                await asyncio.sleep(self.pause)
            try:
                cells = await abysslogs.statistics(self.http, boss)
            except AbyssError as e:
                log.info("Abyss Logs Statistik %s: %s", boss, e)
                continue
            async with self.sessionmaker() as db:
                row = await db.get(ParseBenchmark, boss) or ParseBenchmark(boss=boss)
                row.cells, row.fetched_at = cells, now
                db.add(row)
                await db.commit()
            done += 1
        return done
