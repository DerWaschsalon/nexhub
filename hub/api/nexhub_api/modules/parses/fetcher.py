"""Ranglisten von Abyss Logs für die Parses, im Hintergrund zwischengespeichert.

Alle TICK_SECONDS sucht der Abruf die Paare aus Boss und Klasse, die in getöteten Bossen der Runs der letzten
WINDOW_DAYS Tage vorkommen (calc.needed_pairs). Fällig ist ein Paar ohne Rangliste, eine Rangliste älter als
MAX_AGE und eine leere („not ranked“) älter als EMPTY_MAX_AGE; fehlende zuerst, dann die ältesten, höchstens
PER_TICK je Takt. Zwischen zwei Anfragen liegen PAUSE_SECONDS. Geht etwas schief, bleibt der alte Stand stehen.

Gespeichert werden nur die DPS-Bestwerte je Spieler, keine Namen.
"""
from __future__ import annotations

import asyncio
import logging
import math
import time
from datetime import UTC, datetime, timedelta

import httpx
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from ..bis.abysslogs import REGION, AbyssError, abyss_class, best_per_name, leaderboard_page
from ..logs.models import Run
from .calc import needed_pairs
from .models import ParseBoard

log = logging.getLogger(__name__)

TICK_SECONDS = 600
PER_TICK = 5
PAUSE_SECONDS = 2.0  # Abyss Logs nicht zuschütten
MAX_AGE = timedelta(hours=24)
EMPTY_MAX_AGE = timedelta(days=7)
WINDOW_DAYS = 30
MAX_PAGES = 100  # Sicherung: 10.000 Einträge


async def fetch_board(http: httpx.AsyncClient, cls: str, boss: int, pause: float) -> tuple[int, list[float]]:
    """Alle Seiten der Rangliste; gibt die Gesamtzahl und die Bestwerte je Name aufsteigend zurück."""
    entries, total = await leaderboard_page(http, abyss_class(cls), boss, 1)
    for page in range(2, min(math.ceil(total / 100), MAX_PAGES) + 1):
        await asyncio.sleep(pause)
        more, _ = await leaderboard_page(http, abyss_class(cls), boss, page)
        entries += more
    return total, sorted(float(e.get("dps") or 0) for e in best_per_name(entries))


class ParseFetcher:
    def __init__(self, sessionmaker: async_sessionmaker[AsyncSession], http: httpx.AsyncClient,
                 pause: float = PAUSE_SECONDS) -> None:
        self.sessionmaker, self.http, self.pause = sessionmaker, http, pause

    async def run(self) -> None:
        """Läuft, bis der Hub beendet wird."""
        while True:
            started = time.monotonic()
            try:
                await self.tick()
            except Exception:  # eine kaputte Quelle hält den Abruf nicht für immer an
                log.exception("Parses: Takt abgebrochen")
            await asyncio.sleep(max(0.0, TICK_SECONDS - (time.monotonic() - started)))

    async def tick(self) -> int:
        """Ein Takt; gibt zurück, wie viele Ranglisten neu gespeichert wurden."""
        due = await self._due()
        done = 0
        for i, (boss, cls) in enumerate(due[:PER_TICK]):
            if i:
                await asyncio.sleep(self.pause)
            try:
                total, dps = await fetch_board(self.http, cls, boss, self.pause)
            except AbyssError as e:
                log.info("Parses %s an %s: %s", cls, boss, e)
                continue
            await self._store(boss, cls, total, dps)
            done += 1
        return done

    async def _due(self) -> list[tuple[int, str]]:
        since = int(time.time() * 1000) - WINDOW_DAYS * 86_400_000
        async with self.sessionmaker() as db:
            summaries = (await db.scalars(select(Run.summary).where(Run.start_ms >= since))).all()
            stored = {(b.boss, b.cls): b for b in (await db.scalars(
                select(ParseBoard).where(ParseBoard.region == REGION))).all()}
        now = datetime.now(UTC)
        due: list[tuple[datetime, int, str]] = []
        for boss, cls in needed_pairs(summaries):
            board = stored.get((boss, cls))
            if board is None:
                due.append((datetime.min.replace(tzinfo=UTC), boss, cls))
                continue
            fetched = board.fetched_at if board.fetched_at.tzinfo else board.fetched_at.replace(tzinfo=UTC)
            if now - fetched > (MAX_AGE if board.dps else EMPTY_MAX_AGE):
                due.append((fetched, boss, cls))
        return [(boss, cls) for _, boss, cls in sorted(due)]

    async def _store(self, boss: int, cls: str, total: int, dps: list[float]) -> None:
        async with self.sessionmaker() as db:
            board = await db.scalar(select(ParseBoard).where(
                ParseBoard.boss == boss, ParseBoard.cls == cls, ParseBoard.region == REGION))
            if board is None:
                board = ParseBoard(boss=boss, cls=cls, region=REGION)
                db.add(board)
            board.total, board.dps, board.fetched_at = total, dps, datetime.now(UTC)
            await db.commit()
