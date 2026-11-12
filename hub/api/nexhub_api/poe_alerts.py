"""Preisalarm und Tagespost für Path of Exile, beides über TheWashBot nach Discord.

Alarm: nach jedem Preisabruf (poe_prices.py) wird jeder beobachtete Gegenstand mit seinem Bezugspreis
verglichen. Weicht der Preis um mindestens die Schwelle ab, bekommt der Besitzer eine Meldung, höchstens
eine am Tag; der neue Preis wird dann zum Bezugspreis. Tagespost: einmal am Tag die größten Gewinner und
Verlierer gegenüber dem Vortag. Ohne Discord-Server oder Bot-Verbindung wird nichts geschickt.
"""
from __future__ import annotations

import logging
from dataclasses import asdict, dataclass
from datetime import date, datetime, time, timedelta

import httpx
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from .bot_client import tell_bot
from .config import Settings
from .models import DEFAULT_THRESHOLD as DEFAULT_THRESHOLD  # steht beim Spaltenwert, hier mit angeboten
from .models import PoeItem, PoePrice, PoeWatch, User
from .poe_ninja import Game, ninja_url
from .poe_prices import TZ, existing

log = logging.getLogger(__name__)

DAILY_POST_AT = time(18, 0)  # Uhrzeit der Tagespost in Deutschland
TOP_N = 5
# Gegenstände mit wenig Handel springen zufällig; sie kommen nur mit genug Angeboten oder Umsatz in die Tagespost
MIN_LISTINGS = 10
MIN_TRADE_VOLUME: dict[Game, float] = {"poe1": 1000.0, "poe2": 10.0}

Sessionmaker = async_sessionmaker[AsyncSession]


def change_pct(old: float | None, new: float | None) -> float | None:
    """Änderung in Prozent; ohne beide Preise (oder bei altem Preis 0) gibt es keine."""
    if old is None or new is None or old <= 0:
        return None
    return (new - old) / old * 100


@dataclass(frozen=True)
class Move:
    """Preisänderung eines Gegenstands, so wie sie an den Bot geht."""
    key: str
    name: str
    icon: str | None
    old: float
    new: float
    unit: str
    change: float
    url: str


def move(item: PoeItem, old: float, change: float) -> Move:
    return Move(key=item.key, name=item.name, icon=item.icon, old=old, new=item.price, unit=item.unit,
                change=change, url=ninja_url(item.game, item.league, item.category, item.key))


def check_watch(watch: PoeWatch, item: PoeItem | None, league: str, today: date) -> Move | None:
    """Prüft einen beobachteten Gegenstand und passt seinen Bezugspreis an; gibt den Alarm oder None."""
    if item is None:
        return None
    if watch.ref_league != league:  # neue Liga: andere Preise, kein Vergleich mit der alten
        watch.ref_price, watch.ref_league = item.price, league
        return None
    old = watch.ref_price
    change = change_pct(old, item.price)
    if old is None or change is None or abs(change) < watch.threshold or watch.alerted_on == today:
        return None
    watch.ref_price, watch.alerted_on = item.price, today
    return move(item, old, change)


def is_liquid(item: PoeItem, game: Game) -> bool:
    return (item.listings or 0) >= MIN_LISTINGS or (item.trade_volume or 0) >= MIN_TRADE_VOLUME[game]


def movers(today: list[PoeItem], yesterday: dict[str, float], game: Game) -> tuple[list[Move], list[Move]]:
    """Die TOP_N Gewinner und Verlierer gegenüber dem Vortag, nur Gegenstände mit genug Handel."""
    moves: list[Move] = []
    for item in today:
        change = change_pct(yesterday.get(item.key), item.price)
        if change is not None and is_liquid(item, game):
            moves.append(move(item, yesterday[item.key], change))
    moves.sort(key=lambda m: m.change, reverse=True)
    up = [m for m in moves if m.change > 0][:TOP_N]
    down = [m for m in reversed(moves) if m.change < 0][:TOP_N]
    return up, down


def can_post(settings: Settings) -> bool:
    return settings.bot_configured and settings.hub_guild_id is not None


async def send_alerts(sessionmaker: Sessionmaker, http: httpx.AsyncClient, settings: Settings, game: Game,
                      league: str) -> None:
    """Nach einem Preisabruf: Merklisten prüfen, Bezugspreise speichern, Alarme an den Bot."""
    if not can_post(settings):
        return
    today = datetime.now(TZ).date()
    alerts: list[tuple[int, Move]] = []
    async with sessionmaker() as db:
        rows = (await db.execute(select(PoeWatch, User.discord_id).join(User).where(PoeWatch.game == game))).all()
        items = await existing(db, PoeItem, {watch.key for watch, _ in rows}, PoeItem.game == game,
                               PoeItem.league == league)
        for watch, discord_id in rows:
            alert = check_watch(watch, items.get(watch.key), league, today)
            if alert is not None:
                alerts.append((discord_id, alert))
        await db.commit()
    for discord_id, alert in alerts:
        await tell_bot(http, settings, "poe/alert", {"guild_id": settings.hub_guild_id, "discord_id": discord_id,
                                                     "game": game, "league": league, **asdict(alert)})


async def send_daily(sessionmaker: Sessionmaker, http: httpx.AsyncClient, settings: Settings, game: Game,
                     league: str) -> None:
    """Tagespost: größte Gewinner und Verlierer gegenüber dem Tagespreis von gestern."""
    if not can_post(settings):
        return
    yesterday = datetime.now(TZ).date() - timedelta(days=1)
    async with sessionmaker() as db:
        items = list(await db.scalars(select(PoeItem).where(PoeItem.game == game, PoeItem.league == league)))
        prices = await db.scalars(select(PoePrice).where(PoePrice.game == game, PoePrice.league == league,
                                                         PoePrice.day == yesterday))
        old = {price.key: price.price for price in prices}
    up, down = movers(items, old, game)
    if not up and not down:
        return
    await tell_bot(http, settings, "poe/daily", {"guild_id": settings.hub_guild_id, "game": game, "league": league,
                                                 "up": [asdict(m) for m in up], "down": [asdict(m) for m in down]})
