"""Zählung der Top-Spieler je Klasse für die Bewertung der Ausrüstung (rating.py), einmal je Stunde.

Gezählt wird der Bestand der BiS-Listen (bis_collector.py): bis zu 200 Top-Spieler je Klasse, rollierend
über den Tag gesammelt. Armory und BiS-Listen sehen so dieselben Spieler. Gespeichert wird nur die Zählung
(rating.count_players), keine Namen und keine Profile.

Gezählt werden nur Klassen, die in der Armory vorkommen. Dazu die Würfeltabellen von MetaBot
(metabot.py) für alle Gegenstände der Gezählten und der Armory-Charaktere, je Gegenstand einmal pro
Woche und mit Pause zwischen den Abrufen (Bedingung von MetaBot).
"""
from __future__ import annotations

import asyncio
import logging
from collections import Counter
from datetime import UTC, datetime, timedelta

import httpx
from nexproto.classes import CLASSES
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from . import metabot
from .abysslogs import REGION
from .aion2 import CLASS_KEYS, localized
from .bis_collector import pool
from .bis_stats import MIN_SAMPLE
from .db import aware
from .models import BisSample, Character, ClassCensus, ItemRolls
from .rating import add_tops, count_players

log = logging.getLogger(__name__)

CENSUS_EVERY = timedelta(hours=1)  # der Bestand ändert sich alle 5 Minuten, das Zählen kostet kein Netz
ROLLS_EVERY = timedelta(days=7)
METABOT_PAUSE = 3.0  # Sekunden zwischen zwei Seiten von MetaBot
CHECK_EVERY = 3600  # Sekunden zwischen zwei Blicken auf fällige Klassen


# Klassenname der Website (englisch oder deutsch, auch „Elementalist“) → Schlüssel im Hub
CLASS_BY_NAME = {name.lower(): c.key for c in CLASSES for name in (c.name_en, c.name_de)} | CLASS_KEYS


def character_class(row: Character) -> str | None:
    """Klasse wie im Hub („ranger“); Armory-Einträge haben oft nur den Klassennamen der Website."""
    if row.cls:
        return row.cls
    name = str((localized(row.data or {}, "en").get("profile") or {}).get("class") or "").lower()
    return CLASS_BY_NAME.get(name)


def group_label(samples: list[BisSample]) -> str:
    """Woher die Spieler stammen, z. B. „EU · Ludra · Hard 64 · Normal 136“."""
    raids = Counter(s.raid for s in samples)
    tiers = Counter(s.tier for s in samples)
    parts = [REGION.upper(), raids.most_common(1)[0][0]] + [f"{tier} {n}" for tier, n in sorted(tiers.items())]
    return " · ".join(parts)


class Census:
    """Zählt Klassen im Hintergrund; jede höchstens einmal je Stunde."""

    def __init__(self, sessionmaker: async_sessionmaker[AsyncSession], http: httpx.AsyncClient) -> None:
        self.sessionmaker, self.http = sessionmaker, http

    async def daily(self) -> None:
        """Läuft neben dem Webserver, bis der Hub beendet wird."""
        while True:
            try:
                for cls in await self.due():
                    await self.count(cls)
                await self.load_rolls(await self.armory_items())
            except Exception:  # eine kaputte Quelle hält den Lauf nicht für immer an
                log.exception("Zählung: Lauf abgebrochen")
            await asyncio.sleep(CHECK_EVERY)

    async def due(self, now: datetime | None = None) -> list[str]:
        """Klassen der Armory ohne Zählung oder mit einer älteren als CENSUS_EVERY."""
        limit = (now or datetime.now(UTC)) - CENSUS_EVERY
        async with self.sessionmaker() as db:
            classes = {character_class(row) for row in (await db.scalars(select(Character))).all()}
            fresh = {c.cls for c in (await db.scalars(select(ClassCensus))).all() if aware(c.fetched_at) >= limit}
        return sorted(c for c in classes if c and c not in fresh)

    async def count(self, cls: str) -> None:
        """Eine Klasse aus dem Bestand zählen und speichern. Zu wenige Spieler: vorige Zählung bleibt."""
        async with self.sessionmaker() as db:
            samples = await pool(db, cls)
        if len(samples) < MIN_SAMPLE:
            log.info("Zählung %s: erst %d Spieler im Bestand", cls, len(samples))
            return
        equipments = [localized(s.data, "en").get("equipment") or [] for s in samples]
        items_by_slot: dict[str, set[str]] = {}
        for gear in equipments:
            for item in gear:
                items_by_slot.setdefault(str(item["slot_name"]), set()).add(str(item["name"]))
        rolls = await self.load_rolls({name for names in items_by_slot.values() for name in names})
        data = add_tops({"slots": count_players(equipments)}, items_by_slot, rolls, cls)
        async with self.sessionmaker() as db:
            row = await db.get(ClassCensus, cls) or ClassCensus(cls=cls)
            row.group_label, row.data, row.fetched_at = group_label(samples), data, datetime.now(UTC)
            db.add(row)
            await db.commit()
        log.info("Zählung %s: %d Spieler", cls, len(samples))

    async def armory_items(self) -> set[str]:
        """Englische Namen aller Gegenstände der Armory-Charaktere."""
        async with self.sessionmaker() as db:
            rows = (await db.scalars(select(Character))).all()
        return {str(e["name"]) for row in rows for e in localized(row.data or {}, "en").get("equipment") or []
                if e.get("name")}

    async def load_rolls(self, names: set[str]) -> dict[str, dict]:
        """Würfeltabellen dieser Gegenstände; fehlende oder ältere als eine Woche erst von MetaBot holen."""
        limit = datetime.now(UTC) - ROLLS_EVERY
        async with self.sessionmaker() as db:
            known = {r.name: r for r in (await db.scalars(select(ItemRolls).where(ItemRolls.name.in_(names)))).all()}
            for name in sorted(names):
                row = known.get(name)
                if row is not None and aware(row.fetched_at) >= limit:
                    continue
                try:
                    data: dict | None = await metabot.item(self.http, name)
                except metabot.MetaBotError as e:
                    log.info("MetaBot: %s (%s)", name, e)
                    data = None
                row = row or ItemRolls(name=name)
                row.data, row.fetched_at = data, datetime.now(UTC)
                db.add(row)
                known[name] = row
                await db.commit()
                await asyncio.sleep(METABOT_PAUSE)
        return {name: row.data for name, row in known.items() if row.data}
