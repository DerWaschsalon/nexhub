"""Zählung der Top-Spieler je Klasse für die Bewertung der Ausrüstung (rating.py), einmal am Tag.

Ablauf je Klasse: Rangliste des neuesten Raids mit genug Einträgen von Abyss Logs (abysslogs.py) →
Server über die NC-Suche (die Rangliste nennt keinen) → Ausrüstung mit Werten (NC.gear) → Zählung
(rating.count_players). Gespeichert wird nur die Zählung, keine Namen und keine Profile.

Gezählt werden nur Klassen, die in der Armory vorkommen. Dazu die Würfeltabellen von MetaBot
(metabot.py) für alle Gegenstände der Gezählten und der Armory-Charaktere, je Gegenstand einmal pro
Woche und mit Pause zwischen den Abrufen (Bedingung von MetaBot).
"""
from __future__ import annotations

import asyncio
import logging
from datetime import UTC, datetime, timedelta

import httpx
from nexproto.classes import CLASSES
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from . import metabot
from .abysslogs import REGION, AbyssError, top_players
from .aion2 import CLASS_KEYS, NC, NCError, NotFound, combat_power, localized
from .db import aware
from .models import Character, ClassCensus, ItemRolls
from .rating import add_tops, count_players

log = logging.getLogger(__name__)

PLAYERS = 30  # Top-Spieler je Klasse (Wunsch Navonex)
CENSUS_EVERY = timedelta(days=1)
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


class Census:
    """Zählt Klassen im Hintergrund; jede höchstens einmal am Tag."""

    def __init__(self, sessionmaker: async_sessionmaker[AsyncSession], nc: NC, http: httpx.AsyncClient) -> None:
        self.sessionmaker, self.nc, self.http = sessionmaker, nc, http

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
        """Klassen der Armory ohne Zählung oder mit einer älter als einen Tag."""
        limit = (now or datetime.now(UTC)) - CENSUS_EVERY
        async with self.sessionmaker() as db:
            classes = {character_class(row) for row in (await db.scalars(select(Character))).all()}
            fresh = {c.cls for c in (await db.scalars(select(ClassCensus))).all() if aware(c.fetched_at) >= limit}
        return sorted(c for c in classes if c and c not in fresh)

    async def count(self, cls: str) -> None:
        """Eine Klasse zählen und speichern. Fehler lassen die vorige Zählung stehen."""
        try:
            label, entries = await top_players(self.http, cls, PLAYERS)
        except AbyssError as e:
            log.warning("Zählung %s: %s", cls, e)
            return
        equipments: list[list[dict]] = []
        for entry in entries:
            if len(equipments) >= PLAYERS:
                break
            gear = await self._gear(entry, cls)
            if gear:
                equipments.append(gear)
        if not equipments:
            log.warning("Zählung %s: keine Ausrüstung gefunden", cls)
            return
        items_by_slot: dict[str, set[str]] = {}
        for gear in equipments:
            for item in gear:
                items_by_slot.setdefault(str(item["slot_name"]), set()).add(str(item["name"]))
        rolls = await self.load_rolls({name for names in items_by_slot.values() for name in names})
        data = add_tops({"slots": count_players(equipments)}, items_by_slot, rolls, cls)
        async with self.sessionmaker() as db:
            row = await db.get(ClassCensus, cls) or ClassCensus(cls=cls)
            row.group_label, row.data, row.fetched_at = f"{REGION.upper()} · {label}", data, datetime.now(UTC)
            db.add(row)
            await db.commit()
        log.info("Zählung %s: %d Spieler (%s)", cls, len(equipments), label)

    async def _gear(self, entry: dict, cls: str) -> list[dict] | None:
        """Ausrüstung zu einem Namen der Rangliste. Gibt es den Namen mehrfach, gewinnt die Kampfkraft,
        die der Rangliste am nächsten liegt. Nicht auffindbar: None, der nächste rückt nach."""
        name = entry["playerName"]
        try:
            hits = [h for h in await self.nc.search(name, REGION, cls) if h["name"].casefold() == name.casefold()]
            if len(hits) > 1:
                cp = entry.get("combatPower") or 0
                snaps = [(h, await self.nc.snapshot(h["server_id"], h["character_id"], "en")) for h in hits]
                hits = [min(snaps, key=lambda hs: abs((combat_power(hs[1]) or 0) - cp))[0]]
            if not hits:
                return None
            return await self.nc.gear(hits[0]["server_id"], hits[0]["character_id"])
        except (NotFound, NCError) as e:
            log.info("Zählung: %s übersprungen (%s)", name, e)
            return None

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
