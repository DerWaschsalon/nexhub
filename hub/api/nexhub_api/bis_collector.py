"""Bestand der BiS-Listen: die Top-Spieler je Klasse, rollierend gesammelt und gelesen.

Ablauf: Ist die Warteschlange leer, kommen die Ranglisten von Abyss Logs hinein (abysslogs.top_players,
je Klasse POOL_SIZE Namen). Alle TICK_SECONDS holt der Sammler die PER_TICK besten offenen Namen über alle
Klassen: Name → Server über die NC-Suche → Ausrüstung und Skills in beiden Sprachen (NC.gear). Damit fragen
wir NC über den ganzen Tag verteilt an statt auf einen Schlag, und ein Durchlauf dauert rund anderthalb Tage.

Anlauf: Beim ersten Start und solange eine angefangene Klasse, für die noch Namen warten, weniger als
FILL_BELOW Spieler hat, holt der Sammler FILL_PARALLEL Spieler gleichzeitig und ohne Pause zwischen den Takten. Das
sind rund 4 Anfragen je Sekunde an NC; der Bestand ist so nach etwa 7 Stunden voll statt nach Tagen.

Der Bestand hat höchstens POOL_SIZE Spieler je Klasse, jeden genau einmal (Schlüssel aus Server und
Charakter-ID, kein Name). Wer schon drin ist, wird aktualisiert; ein Neuer ersetzt bei vollem Bestand den
ältesten. So ergibt sich ein gleitender Durchschnitt statt eines harten Tageswechsels.

Aus dem Bestand rechnen die BiS-Listen (bis_stats.py, routes/bis.py) und die Zählung für die Bewertung
der Armory (census.py).
"""
from __future__ import annotations

import asyncio
import hashlib
import logging
import time
from datetime import UTC, datetime

import httpx
from nexproto.classes import CLASS_KEYS
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from .abysslogs import REGION, AbyssError, top_players
from .aion2 import FORMAT, LANGS, NC, NCError, NotFound, combat_power
from .models import BisQueue, BisSample

log = logging.getLogger(__name__)

TICK_SECONDS = 300
PER_TICK = 4
POOL_SIZE = 200  # Spieler je Klasse (Fabio 10.11.: 50 sind zu wenig)
MAX_TRIES = 3  # NC-Fehler: so oft versuchen, dann den Namen verwerfen
FILL_BELOW = 150  # Anlauf, solange eine Klasse weniger hat (ein paar Namen findet die NC-Suche nie)
FILL_PARALLEL = 5  # Spieler gleichzeitig im Anlauf; je Spieler rund 50 Anfragen in einer Minute


def character_key(server_id: int, character_id: str) -> str:
    return hashlib.sha256(f"{server_id}:{character_id}".encode()).hexdigest()


async def pool(db: AsyncSession, cls: str) -> list[BisSample]:
    """Der Bestand einer Klasse."""
    return list((await db.scalars(select(BisSample).where(BisSample.cls == cls))).all())


class BisCollector:
    """Füllt Warteschlange und Bestand im Hintergrund, neben dem Webserver."""

    def __init__(self, sessionmaker: async_sessionmaker[AsyncSession], nc: NC, http: httpx.AsyncClient) -> None:
        self.sessionmaker, self.nc, self.http = sessionmaker, nc, http

    async def run(self) -> None:
        """Läuft, bis der Hub beendet wird. Die Warteschlange liegt in der Datenbank: nach einem
        Neustart geht es beim nächsten Takt einfach weiter."""
        while True:
            started = time.monotonic()
            filling = False
            try:
                filling = await self.tick()
            except Exception:  # eine kaputte Quelle hält den Sammler nicht für immer an
                log.exception("BiS: Takt abgebrochen")
            if filling:
                continue
            # Takt von Beginn zu Beginn: ein Spieler braucht rund eine Minute bei NC
            await asyncio.sleep(max(0.0, TICK_SECONDS - (time.monotonic() - started)))

    async def tick(self) -> bool:
        """Ein Takt. Gibt zurück, ob der Sammler noch im Anlauf ist (dann geht es ohne Pause weiter)."""
        if not await self._next(1):
            await self.refill()
        if not await self._filling():
            for row in await self._next(PER_TICK):
                await self.collect(row)
            return False
        await asyncio.gather(*(self.collect(row) for row in await self._next(FILL_PARALLEL)))
        return True

    async def _next(self, count: int) -> list[BisQueue]:
        async with self.sessionmaker() as db:
            return list((await db.scalars(select(BisQueue).order_by(BisQueue.rank, BisQueue.id).limit(count))).all())

    async def _filling(self) -> bool:
        """Anlauf: Der Bestand ist noch ganz leer, oder eine angefangene Klasse, für die noch Namen warten, hat
        weniger als FILL_BELOW Spieler. Klassen ohne einen einzigen Treffer zählen nicht, sonst liefe der Anlauf
        ewig; da der Bestand nie schrumpft, endet er sicher."""
        async with self.sessionmaker() as db:
            waiting = set((await db.scalars(select(BisQueue.cls).distinct())).all())
            rows = await db.execute(select(BisSample.cls, func.count()).group_by(BisSample.cls))
        sizes = {cls: count for cls, count in rows}
        if not sizes:
            return bool(waiting)
        return any(cls in sizes and sizes[cls] < FILL_BELOW for cls in waiting)

    async def refill(self) -> None:
        """Neue Ranglisten für alle Klassen. Klassen ohne genug Einträge (z. B. Faustkämpfer) fehlen."""
        rows = []
        for cls in CLASS_KEYS:
            try:
                raid, entries = await top_players(self.http, cls, POOL_SIZE)
            except AbyssError as e:
                log.info("BiS %s: %s", cls, e)
                continue
            rows += [BisQueue(cls=cls, player_name=e["playerName"], raid=raid, tier=e["tier"], rank=rank,
                              combat_power=e.get("combatPower"), tries=0)
                     for rank, e in enumerate(entries)]
        async with self.sessionmaker() as db:
            db.add_all(rows)
            await db.commit()
        log.info("BiS: %d Namen in der Warteschlange", len(rows))

    async def collect(self, row: BisQueue) -> None:
        """Einen Namen abrufen und ablegen. Nicht gefunden: verwerfen. NC-Fehler: später noch einmal."""
        async with self.sessionmaker() as db:
            row = await db.get(BisQueue, row.id)  # frisch laden: die Versuche zählen in der Datenbank
            if row is None:
                return
            try:
                hit = await self.resolve(row.player_name, row.cls, row.combat_power)
                if hit:
                    await self._store(db, row, hit)
            except NotFound:
                pass
            except NCError as e:
                row.tries += 1
                if row.tries < MAX_TRIES:
                    log.info("BiS: %s später noch einmal (%s)", row.player_name, e)
                    await db.commit()
                    return
            await db.delete(row)
            await db.commit()

    async def resolve(self, name: str, cls: str, cp: int | None) -> dict | None:
        """Treffer der NC-Suche zu einem Namen der Rangliste (die nennt keinen Server). Gibt es den Namen
        mehrfach, gewinnt die Kampfkraft, die der Rangliste am nächsten liegt."""
        hits = [h for h in await self.nc.search(name, REGION, cls) if h["name"].casefold() == name.casefold()]
        if len(hits) <= 1:
            return hits[0] if hits else None
        snaps = [(h, await self.nc.snapshot(h["server_id"], h["character_id"], "en")) for h in hits]
        return min(snaps, key=lambda hs: abs((combat_power(hs[1]) or 0) - (cp or 0)))[0]

    async def _store(self, db: AsyncSession, row: BisQueue, hit: dict) -> None:
        data: dict = {"v": FORMAT}
        for lang in LANGS:
            data[lang] = await self.nc.gear(hit["server_id"], hit["character_id"], lang)
        key = character_key(hit["server_id"], hit["character_id"])
        sample = await db.scalar(select(BisSample).where(BisSample.character_key == key))
        if sample is None:
            await self._make_room(db, row.cls)
            sample = BisSample(cls=row.cls, character_key=key)
            db.add(sample)
        sample.raid, sample.tier, sample.combat_power = row.raid, row.tier, row.combat_power
        sample.data, sample.fetched_at = data, datetime.now(UTC)

    async def _make_room(self, db: AsyncSession, cls: str) -> None:
        """Bei vollem Bestand fällt der älteste Spieler der Klasse heraus."""
        count = await db.scalar(select(func.count()).select_from(BisSample).where(BisSample.cls == cls))
        if (count or 0) < POOL_SIZE:
            return
        oldest = await db.scalar(select(BisSample).where(BisSample.cls == cls).order_by(BisSample.fetched_at).limit(1))
        await db.delete(oldest)
