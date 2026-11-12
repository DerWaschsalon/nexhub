"""Preise von poe.ninja speichern: aktueller Preis je Gegenstand (poe_items) und ein Tagespreis (poe_prices).

Läuft stündlich je Spiel neben dem Webserver (main.py, nur mit hub_poe_enabled). Kategorien werden
nacheinander abgerufen. Scheitert eine Kategorie (Netz, HTTP-Fehler, geändertes Format), bleiben ihre
alten Werte stehen und die übrigen laufen weiter. Gegenstände, die in einem Abruf fehlen, bleiben
unverändert; poe.ninja lässt Gegenstände mit zu wenig Handel zeitweise weg.
"""
from __future__ import annotations

import asyncio
import logging
from collections.abc import Awaitable, Callable, Iterable
from datetime import UTC, datetime
from itertools import batched
from typing import TypeVar
from zoneinfo import ZoneInfo

from sqlalchemy import ColumnElement, select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from .config import Settings
from .models import PoeItem, PoePrice
from .poe_ninja import (EXCHANGE_TYPES, GAMES, STASH_TYPES, Game, PoeNinja, PoeNinjaError, PriceLine,
                        parse_exchange, parse_stash)

log = logging.getLogger(__name__)
Row = TypeVar("Row", PoeItem, PoePrice)

REFRESH_EVERY_S = 3600  # poe.ninja erneuert PoE 2 etwa stündlich; öfter bringt keine frischeren Daten
TZ = ZoneInfo("Europe/Berlin")  # der Tagespreis gilt für den Kalendertag in Deutschland
KEYS_PER_QUERY = 1000
PARSERS = {"exchange": parse_exchange, "stash": parse_stash}


async def existing(db: AsyncSession, model: type[Row], keys: Iterable[str],
                   *where: ColumnElement[bool]) -> dict[str, Row]:
    """Vorhandene Zeilen je Kennung, in Blöcken: große Kategorien (PoE 1 BaseType, SkillGem) sprengen als
    eine IN-Liste sonst die Parametergrenze von Postgres (32767)."""
    rows: dict[str, Row] = {}
    for chunk in batched(keys, KEYS_PER_QUERY):
        found = await db.scalars(select(model).where(*where, model.key.in_(chunk)))
        rows.update((row.key, row) for row in found)
    return rows


class PoePrices:
    def __init__(self, sessionmaker: async_sessionmaker[AsyncSession], ninja: PoeNinja, settings: Settings) -> None:
        self.sessionmaker, self.ninja, self.settings = sessionmaker, ninja, settings

    async def league(self, game: Game) -> str:
        """Festgelegte Liga aus den Einstellungen, sonst die aktuelle Challenge-Liga von poe.ninja."""
        fixed = {"poe1": self.settings.hub_poe1_league, "poe2": self.settings.hub_poe2_league}[game]
        if fixed:
            return fixed
        leagues = await self.ninja.leagues(game)
        if not leagues:
            raise PoeNinjaError(f"{game}: keine Liga")
        return leagues[0]

    async def refresh(self, game: Game) -> str:
        """Alle Kategorien des Spiels abrufen und speichern; gibt die Liga zurück."""
        league = await self.league(game)
        for kind, categories in (("exchange", EXCHANGE_TYPES[game]), ("stash", STASH_TYPES[game])):
            for category in categories:
                try:
                    data = await self.ninja.overview(game, kind, league, category)
                    await self.store(game, league, PARSERS[kind](game, league, category, data))
                except PoeNinjaError as error:  # eine kaputte Kategorie hält die übrigen nicht auf
                    log.warning("poe.ninja: %s %s %s übersprungen: %s", game, kind, category, error)
                except Exception:
                    log.exception("poe.ninja: %s %s %s übersprungen", game, kind, category)
        return league

    async def store(self, game: Game, league: str, lines: list[PriceLine]) -> None:
        """Aktuellen Preis und Tagespreis von heute setzen; in einer Transaktion je Kategorie."""
        by_key = {line.key: line for line in lines}  # doppelte Kennung: die letzte Zeile gilt
        now = datetime.now(UTC)
        today = now.astimezone(TZ).date()
        async with self.sessionmaker() as db:
            items = await existing(db, PoeItem, by_key, PoeItem.game == game, PoeItem.league == league)
            days = await existing(db, PoePrice, by_key, PoePrice.game == game, PoePrice.league == league,
                                  PoePrice.day == today)
            for key, line in by_key.items():
                item = items.get(key) or PoeItem(game=game, league=league, key=key)
                item.name, item.category, item.icon, item.price = line.name, line.category, line.icon, line.price
                item.unit, item.listings, item.trade_volume = line.unit, line.listings, line.trade_volume
                item.updated_at = now
                day = days.get(key) or PoePrice(game=game, league=league, key=key, day=today)
                day.price = line.price
                db.add_all([item, day])
            await db.commit()

    async def run(self, after_refresh: Callable[[Game, str], Awaitable[None]]) -> None:
        """Läuft neben dem Webserver, bis der Hub beendet wird."""
        while True:
            for game in GAMES:
                try:
                    league = await self.refresh(game)
                    await after_refresh(game, league)
                except Exception:  # z. B. poe.ninja nicht erreichbar; nächster Versuch in einer Stunde
                    log.exception("poe.ninja: Abruf für %s abgebrochen", game)
            await asyncio.sleep(REFRESH_EVERY_S)
