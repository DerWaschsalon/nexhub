"""Armory: eingetragene Charaktere, einmal täglich und auf Knopfdruck neu von der AION-2-Website.

Abruf und Speicherformat sind dieselben wie bei den Mitspielern eines Runs (characters.fill), hier
immer mit den Werten je Gegenstand (bei Runs nur auf Knopfdruck, characters.load_details). Nach
jedem gelungenen Abruf steht Kampfkraft und Item-Level des Tages in `character_days` (Verlauf).
Der tägliche Lauf sieht stündlich nach, wessen letzter Abruf älter als einen Tag ist – so holt er
nach einem Neustart nach, ohne alle auf einmal abzurufen.
"""
from __future__ import annotations

import asyncio
import logging
from datetime import UTC, datetime, timedelta

from sqlalchemy import or_, select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from .aion2 import NC
from .characters import fill
from .models import Character, CharacterDay

log = logging.getLogger(__name__)

DAILY = timedelta(days=1)
CHECK_EVERY = 3600  # Sekunden zwischen zwei Blicken auf fällige Charaktere


async def record_day(db: AsyncSession, row: Character) -> None:
    """Kennzahlen des Abruftags festhalten; ein zweiter Abruf am selben Tag überschreibt sie."""
    if row.status != "ok" or row.fetched_at is None:
        return
    day = row.fetched_at.astimezone(UTC).date()
    entry = await db.scalar(select(CharacterDay).where(CharacterDay.character_id == row.id, CharacterDay.day == day))
    if entry is None:
        entry = CharacterDay(character_id=row.id, day=day)
        db.add(entry)
    entry.combat_power, entry.item_level = row.combat_power, row.item_level


class Armory:
    """Ruft Charaktere einzeln ab; derselbe Charakter läuft nie doppelt."""

    def __init__(self, sessionmaker: async_sessionmaker[AsyncSession], nc: NC) -> None:
        self.sessionmaker, self.nc = sessionmaker, nc
        self.running: set[int] = set()

    async def refresh(self, character_id: int) -> None:
        if character_id in self.running:
            return
        self.running.add(character_id)
        try:
            async with self.sessionmaker() as db:
                row = await db.get(Character, character_id)
                if row is None:  # inzwischen entfernt
                    return
                await fill(self.nc, row, f"Armory {character_id}", items=True)
                await record_day(db, row)
                await db.commit()
        finally:
            self.running.discard(character_id)

    async def due(self, now: datetime | None = None) -> list[int]:
        """Noch nie oder vor mehr als einem Tag abgerufen, älteste zuerst – dazu alles, was noch auf
        `offen` steht (ein Neustart hat den Abruf unterbrochen)."""
        limit = (now or datetime.now(UTC)) - DAILY
        async with self.sessionmaker() as db:
            return list((await db.scalars(select(Character.id).where(
                or_(Character.fetched_at.is_(None), Character.fetched_at < limit, Character.status == "offen"))
                .order_by(Character.fetched_at.nulls_first()))).all())

    async def daily(self) -> None:
        """Läuft neben dem Webserver, bis der Hub beendet wird."""
        while True:
            for character_id in await self.due():
                try:
                    await self.refresh(character_id)
                except Exception:  # ein kaputter Charakter hält die anderen nicht auf
                    log.exception("Armory: Charakter %d nicht abgerufen", character_id)
            await asyncio.sleep(CHECK_EVERY)
