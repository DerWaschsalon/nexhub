"""Preise von poe.ninja speichern: aktueller Preis je Gegenstand (poe_items) und ein Tagespreis (poe_prices).

Läuft stündlich je Spiel neben dem Webserver (main.py, nur mit hub_poe_enabled), nach einem Neustart erst
eine Stunde nach dem letzten gespeicherten Abruf. Kategorien werden nacheinander abgerufen; antwortet
poe.ninja mit 403/429, fällt der Rest des Spiels aus, bis Retry-After (mindestens die Stunde) vorbei ist.
Scheitert eine Kategorie (Netz, HTTP-Fehler, geändertes Format), bleiben ihre alten Werte stehen und die
übrigen laufen weiter. Bei 304 (unverändert) wird nichts neu geschrieben. Gegenstände, die in einem Abruf
fehlen, bleiben unverändert; poe.ninja lässt Gegenstände mit zu wenig Handel zeitweise weg.
"""
from __future__ import annotations

import asyncio
import logging
import time
from collections.abc import Awaitable, Callable, Iterable
from datetime import UTC, datetime
from itertools import batched
from typing import Literal, TypeVar
from zoneinfo import ZoneInfo

from sqlalchemy import ColumnElement, func, select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from .config import Settings
from .models import PoeItem, PoePrice
from .poe_ninja import (CATEGORIES, GAMES, Game, PoeNinja, PoeNinjaBlocked, PoeNinjaError, PriceLine,
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
        self.leagues: dict[Game, str] = {}  # Liga des letzten Abrufs je Spiel
        self.due: dict[Game, float] = {}  # nächster Abruf je Spiel (Unix-Zeit); fehlt: sofort

    def fixed_league(self, game: Game) -> str:
        """Festgelegte Liga aus den Einstellungen, leer ohne."""
        return {"poe1": self.settings.hub_poe1_league, "poe2": self.settings.hub_poe2_league}[game]

    def last_league(self, game: Game) -> str | None:
        """Liga des letzten Abrufs; None, solange das Spiel noch nicht abgerufen wurde."""
        return self.leagues.get(game)

    def known_league(self, game: Game) -> str | None:
        """Liga für Anfragen, ohne poe.ninja zu fragen: letzter Abruf, sonst die festgelegte; None: lädt noch."""
        return self.last_league(game) or self.fixed_league(game) or None

    async def league(self, game: Game) -> str:
        """Festgelegte Liga aus den Einstellungen, sonst die aktuelle Challenge-Liga von poe.ninja."""
        fixed = self.fixed_league(game)
        if fixed:
            return fixed
        leagues = await self.ninja.leagues(game)
        if leagues is None and game in self.leagues:  # 304: Ligen unverändert
            return self.leagues[game]
        if not leagues:
            raise PoeNinjaError(f"{game}: keine Liga")
        return leagues[0]

    async def resume(self) -> None:
        """Nach einem Neustart: Liga und Zeitpunkt des letzten Abrufs je Spiel aus der Datenbank, damit der
        Start poe.ninja nicht sofort wieder abfragt. Wurde die festgelegte Liga geändert, gleich abrufen."""
        async with self.sessionmaker() as db:
            for game in GAMES:
                newest = await db.scalar(select(func.max(PoeItem.updated_at)).where(PoeItem.game == game))
                if newest is None:
                    continue
                league = await db.scalar(select(PoeItem.league).where(PoeItem.game == game,
                                                                       PoeItem.updated_at == newest).limit(1))
                fixed = self.fixed_league(game)
                if league is None or (fixed and fixed != league):
                    continue
                if newest.tzinfo is None:  # SQLite gibt die Zeit ohne Zone zurück, gespeichert ist UTC
                    newest = newest.replace(tzinfo=UTC)
                self.leagues[game] = league
                self.due[game] = newest.timestamp() + REFRESH_EVERY_S

    async def refresh(self, game: Game) -> str | None:
        """Alle Kategorien des Spiels abrufen und speichern; gibt die Liga zurück (None ohne Liga)."""
        self.due[game] = time.time() + REFRESH_EVERY_S
        try:
            league = await self.league(game)
            self.leagues[game] = league  # Anfragen kennen die Liga schon während des Abrufs
            for kind, category in CATEGORIES[game]:
                await self.refresh_category(game, league, kind, category)
        except PoeNinjaBlocked as error:
            log.warning("poe.ninja: %s abgebrochen, poe.ninja will weniger Last: %s", game, error)
            self.due[game] = max(self.due[game], time.time() + error.retry_after)
        return self.last_league(game)

    async def refresh_category(self, game: Game, league: str, kind: Literal["exchange", "stash"],
                               category: str) -> None:
        """Eine Kategorie; ein Fehler hier hält die übrigen nicht auf, nur 403/429 bricht ab."""
        try:
            data = await self.ninja.overview(game, kind, league, category)
            if data is None:
                await self.keep_days(game, league, category)
            else:
                await self.store(game, league, PARSERS[kind](game, league, category, data))
        except PoeNinjaBlocked:
            raise
        except PoeNinjaError as error:
            log.warning("poe.ninja: %s %s %s übersprungen: %s", game, kind, category, error)
        except Exception:
            self.ninja.forget(game, kind, league, category)  # beim nächsten Mal die ganze Antwort holen
            log.exception("poe.ninja: %s %s %s übersprungen", game, kind, category)

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

    async def keep_days(self, game: Game, league: str, category: str) -> None:
        """304, Preise unverändert: nur fehlende Tagespreise von heute aus dem aktuellen Preis anlegen
        (der erste Abruf nach Mitternacht kann unverändert sein)."""
        today = datetime.now(TZ).date()
        async with self.sessionmaker() as db:
            items = list(await db.scalars(select(PoeItem).where(PoeItem.game == game, PoeItem.league == league,
                                                               PoeItem.category == category)))
            days = await existing(db, PoePrice, [item.key for item in items], PoePrice.game == game,
                                  PoePrice.league == league, PoePrice.day == today)
            db.add_all(PoePrice(game=game, league=league, key=item.key, day=today, price=item.price)
                       for item in items if item.key not in days)
            await db.commit()

    def seconds_to_next(self) -> float:
        """Sekunden bis zum nächsten fälligen Spiel."""
        return max(0.0, min(self.due.get(game, 0.0) for game in GAMES) - time.time())

    async def run(self, after_refresh: Callable[[Game, str], Awaitable[None]]) -> None:
        """Läuft neben dem Webserver, bis der Hub beendet wird."""
        try:
            await self.resume()
        except Exception:  # z. B. Datenbank nicht erreichbar; dann eben gleich abrufen
            log.exception("poe.ninja: letzter Abruf nicht lesbar")
        while True:
            for game in GAMES:
                if time.time() < self.due.get(game, 0.0):
                    continue
                try:
                    league = await self.refresh(game)
                    if league is not None:
                        await after_refresh(game, league)
                except Exception:  # z. B. poe.ninja nicht erreichbar; nächster Versuch in einer Stunde
                    log.exception("poe.ninja: Abruf für %s abgebrochen", game)
            await asyncio.sleep(self.seconds_to_next())
