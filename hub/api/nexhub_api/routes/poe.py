"""Path of Exile: Preise suchen und eine Merkliste führen (Web), Preisabfragen für den Bot (intern).

    GET    /api/poe/search?game=&q=            Gegenstände der aktuellen Liga suchen (höchstens 20)
    GET    /api/poe/watches?game=              eigene Merkliste mit Preis, Änderung und Tagesverlauf
    POST   /api/poe/watches                    Gegenstand merken (Alarmschwelle in Prozent, Standard 20)
    PATCH  /api/poe/watches/{id}               Schwelle ändern
    DELETE /api/poe/watches/{id}               aus der Merkliste nehmen
    GET    /api/internal/poe/price?game=&q=    bester Treffer mit Preis (nur Bot, Schlüssel)
    GET    /api/internal/poe/complete?game=&q= Namensvorschläge für die Autovervollständigung (nur Bot)

/api/internal/… ist im Caddy gesperrt und nur im Docker-Netz erreichbar. Ohne hub_poe_enabled antwortet alles 404.
Preise, Liga und Tagesverlauf kommen aus poe_prices.py.
"""
from __future__ import annotations

from datetime import date, datetime, timedelta
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query, Request, Response
from pydantic import BaseModel, Field
from sqlalchemy import ColumnElement, case, func, select
from sqlalchemy.exc import IntegrityError

from ..deps import DB, BotKey, CurrentUser
from ..models import DEFAULT_THRESHOLD, PoeItem, PoePrice, PoeWatch
from ..poe_alerts import change_pct
from ..poe_ninja import Game, ninja_url
from ..poe_prices import TZ, PoePrices

SEARCH_LIMIT = 20
COMPLETE_LIMIT = 25


def prices_service(request: Request) -> PoePrices:
    prices = request.app.state.poe_prices
    if prices is None:
        raise HTTPException(404, "Path of Exile ist nicht eingeschaltet")
    return prices


Prices = Annotated[PoePrices, Depends(prices_service)]
router = APIRouter(prefix="/api/poe", tags=["poe"], dependencies=[Depends(prices_service)])
internal = APIRouter(prefix="/api/internal/poe", tags=["poe-internal"], dependencies=[Depends(prices_service)])


async def current_league(prices: PoePrices, game: Game) -> str:
    return prices.last_league(game) or await prices.league(game)


def like(text: str) -> str:
    """Suchtext als LIKE-Muster, `%`, `_` und `\\` wörtlich (escape="\\\\" beim Vergleich)."""
    return text.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")


def named(game: Game, league: str, q: str) -> list[ColumnElement[bool]]:
    return [PoeItem.game == game, PoeItem.league == league, PoeItem.name.ilike(f"%{like(q)}%", escape="\\")]


def best_first(q: str) -> list[ColumnElement]:
    """Reihenfolge: genauer Name, dann Anfang, dann enthält; je Stufe der höchste Preis zuerst."""
    rank = case((func.lower(PoeItem.name) == q.lower(), 0),
                (PoeItem.name.ilike(f"{like(q)}%", escape="\\"), 1), else_=2)
    return [rank, PoeItem.price.desc(), PoeItem.name]


async def days_before(db: DB, game: Game, league: str, keys: list[str], today: date, ago: int) -> dict[str, float]:
    rows = await db.execute(select(PoePrice.key, PoePrice.price).where(
        PoePrice.game == game, PoePrice.league == league, PoePrice.key.in_(keys),
        PoePrice.day == today - timedelta(days=ago)))
    return {key: price for key, price in rows}


class Found(BaseModel):
    key: str
    name: str
    category: str
    icon: str | None
    price: float
    unit: str


@router.get("/search")
async def search(game: Game, user: CurrentUser, db: DB, prices: Prices,
                 q: Annotated[str, Query(min_length=1, max_length=100)]) -> list[Found]:
    league = await current_league(prices, game)
    items = await db.scalars(select(PoeItem).where(*named(game, league, q)).order_by(*best_first(q))
                             .limit(SEARCH_LIMIT))
    return [Found.model_validate(i, from_attributes=True) for i in items]


class Day(BaseModel):
    day: date
    price: float


class WatchOut(BaseModel):
    id: int
    key: str
    name: str
    icon: str | None
    price: float | None
    change_24h: float | None
    change_7d: float | None
    threshold: float
    url: str | None
    days: list[Day]


class WatchList(BaseModel):
    league: str
    unit: str | None  # Währung der Preise; None, solange die Liste leer ist oder keine Preise hat
    watches: list[WatchOut]


async def watch_list(db: DB, prices: PoePrices, game: Game, user_id: int, only: int | None = None) -> WatchList:
    league = await current_league(prices, game)
    query = select(PoeWatch).where(PoeWatch.user_id == user_id, PoeWatch.game == game).order_by(PoeWatch.name)
    if only is not None:
        query = query.where(PoeWatch.id == only)
    watches = list((await db.scalars(query)).all())
    keys = [w.key for w in watches]
    items = {i.key: i for i in await db.scalars(
        select(PoeItem).where(PoeItem.game == game, PoeItem.league == league, PoeItem.key.in_(keys)))}
    today = datetime.now(TZ).date()
    yesterday = await days_before(db, game, league, keys, today, 1)
    last_week = await days_before(db, game, league, keys, today, 7)
    history: dict[str, list[Day]] = {}
    for key, day, price in await db.execute(
            select(PoePrice.key, PoePrice.day, PoePrice.price)
            .where(PoePrice.game == game, PoePrice.league == league, PoePrice.key.in_(keys))
            .order_by(PoePrice.day)):
        history.setdefault(key, []).append(Day(day=day, price=price))
    out = []
    for w in watches:
        item = items.get(w.key)
        out.append(WatchOut(
            id=w.id, key=w.key, name=w.name, icon=item.icon if item else None,
            price=item.price if item else None,
            change_24h=change_pct(yesterday.get(w.key), item.price) if item else None,
            change_7d=change_pct(last_week.get(w.key), item.price) if item else None,
            threshold=w.threshold, url=ninja_url(game, league, item.category, w.key) if item else None,
            days=history.get(w.key, [])))
    unit = next((i.unit for i in items.values()), None)
    return WatchList(league=league, unit=unit, watches=out)


@router.get("/watches")
async def watches(game: Game, user: CurrentUser, db: DB, prices: Prices) -> WatchList:
    return await watch_list(db, prices, game, user.id)


class WatchIn(BaseModel):
    game: Game
    key: str = Field(min_length=1, max_length=128)
    threshold: float = Field(DEFAULT_THRESHOLD, ge=1, le=1000)


class ThresholdIn(BaseModel):
    threshold: float = Field(ge=1, le=1000)


@router.post("/watches", status_code=201)
async def add_watch(body: WatchIn, user: CurrentUser, db: DB, prices: Prices) -> WatchOut:
    league = await current_league(prices, body.game)
    item = await db.scalar(select(PoeItem).where(PoeItem.game == body.game, PoeItem.league == league,
                                                 PoeItem.key == body.key))
    if item is None:
        raise HTTPException(404, "Gegenstand in dieser Liga unbekannt")
    if await db.scalar(select(PoeWatch.id).where(PoeWatch.user_id == user.id, PoeWatch.game == body.game,
                                                 PoeWatch.key == body.key)):
        raise HTTPException(409, "Schon auf der Merkliste")
    # Der Alarm vergleicht mit dem Preis von heute (poe_alerts.py)
    entry = PoeWatch(user_id=user.id, game=body.game, key=item.key, name=item.name, threshold=body.threshold,
                     ref_price=item.price, ref_league=league)
    db.add(entry)
    try:
        await db.commit()
    except IntegrityError:  # zwei Anfragen gleichzeitig
        raise HTTPException(409, "Schon auf der Merkliste") from None
    return (await watch_list(db, prices, body.game, user.id, only=entry.id)).watches[0]


async def own_watch(db: DB, user_id: int, watch_id: int) -> PoeWatch:
    entry = await db.scalar(select(PoeWatch).where(PoeWatch.id == watch_id, PoeWatch.user_id == user_id))
    if entry is None:
        raise HTTPException(404, "Eintrag nicht gefunden")
    return entry


@router.patch("/watches/{watch_id}")
async def set_threshold(watch_id: int, body: ThresholdIn, user: CurrentUser, db: DB, prices: Prices) -> WatchOut:
    entry = await own_watch(db, user.id, watch_id)
    entry.threshold = body.threshold
    await db.commit()
    return (await watch_list(db, prices, entry.game, user.id, only=entry.id)).watches[0]


@router.delete("/watches/{watch_id}", status_code=204)
async def delete_watch(watch_id: int, user: CurrentUser, db: DB) -> Response:
    await db.delete(await own_watch(db, user.id, watch_id))
    await db.commit()
    return Response(status_code=204)


class PriceOut(BaseModel):
    name: str
    price: float
    unit: str
    change_24h: float | None
    change_7d: float | None
    league: str
    url: str
    icon: str | None


@internal.get("/price")
async def price(game: Game, key: BotKey, db: DB, prices: Prices,
                q: Annotated[str, Query(min_length=1, max_length=100)]) -> PriceOut:
    league = await current_league(prices, game)
    item = await db.scalar(select(PoeItem).where(*named(game, league, q)).order_by(*best_first(q)).limit(1))
    if item is None:
        raise HTTPException(404, "Nichts gefunden")
    today = datetime.now(TZ).date()
    before = [(await days_before(db, game, league, [item.key], today, n)).get(item.key) for n in (1, 7)]
    return PriceOut(name=item.name, price=item.price, unit=item.unit, league=league, icon=item.icon,
                    change_24h=change_pct(before[0], item.price), change_7d=change_pct(before[1], item.price),
                    url=ninja_url(game, league, item.category, item.key))


@internal.get("/complete")
async def complete(game: Game, key: BotKey, db: DB, prices: Prices,
                   q: Annotated[str, Query(max_length=100)] = "") -> list[str]:
    # Ohne q (leeres Discord-Eingabefeld) kommen absichtlich die 25 teuersten Namen
    league = await current_league(prices, game)
    names = await db.scalars(select(PoeItem.name).where(*named(game, league, q)).order_by(*best_first(q))
                             .limit(COMPLETE_LIMIT))
    return [name[:100] for name in names]
