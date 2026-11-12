"""Preisalarm und Tagespost für Path of Exile: Regeln ohne Netz, Versand über die gefälschte Bot-API."""
from __future__ import annotations

import asyncio
import json
from datetime import UTC, date, datetime, timedelta

import httpx
import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from nexhub_api.config import Settings
from nexhub_api.main import seconds_until_daily_post
from nexhub_api.models import PoeItem, PoePrice, PoeWatch, User
from nexhub_api.poe_alerts import TOP_N, check_watch, movers, send_alerts, send_daily
from nexhub_api.poe_prices import TZ

from .conftest import GUILD, FakeDiscord
from .test_bot import BOT

TODAY = date(2026, 11, 12)
LEAGUE = "Standard"


def item(**over) -> PoeItem:
    fields = dict(game="poe1", league=LEAGUE, key="divine-orb", name="Divine Orb", category="Currency",
                  price=125.0, unit="chaos", listings=50, trade_volume=None, updated_at=datetime.now(UTC))
    return PoeItem(**{**fields, **over})


def watch(**over) -> PoeWatch:
    fields = dict(game="poe1", key="divine-orb", name="Divine Orb", threshold=20.0, ref_price=100.0,
                  ref_league=LEAGUE, alerted_on=None)
    return PoeWatch(**{**fields, **over})


def test_alert_over_threshold():
    entry = watch()
    move = check_watch(entry, item(), LEAGUE, TODAY)
    assert move is not None and move.change == 25.0 and move.old == 100.0 and move.new == 125.0
    assert entry.ref_price == 125.0 and entry.alerted_on == TODAY


def test_alert_once_per_day():
    entry = watch()
    check_watch(entry, item(), LEAGUE, TODAY)
    assert check_watch(entry, item(price=160.0), LEAGUE, TODAY) is None


def test_no_alert_on_league_change():
    entry = watch(ref_league="Alt")
    assert check_watch(entry, item(league="Neu", price=1.0), "Neu", TODAY) is None
    assert entry.ref_price == 1.0 and entry.ref_league == "Neu"


@pytest.mark.parametrize("ref_price", [None, 0.0, -1.0])
def test_reset_without_ref_price(ref_price):
    """Ohne brauchbaren Bezugspreis wie bei einer neuen Liga: heutigen Preis merken, kein Alarm."""
    entry = watch(ref_price=ref_price)
    assert check_watch(entry, item(), LEAGUE, TODAY) is None
    assert entry.ref_price == 125.0 and entry.alerted_on is None


def test_no_alert_without_price():
    entry = watch()
    assert check_watch(entry, None, LEAGUE, TODAY) is None
    assert entry.ref_price == 100.0 and entry.ref_league == LEAGUE and entry.alerted_on is None


def test_movers_skip_thin_items():
    thin = item(key="thin", price=600.0, listings=1)
    liquid = item(key="liquid", price=130.0, listings=50)
    up, down = movers([thin, liquid], {"thin": 100.0, "liquid": 100.0}, "poe1")
    assert [m.key for m in up] == ["liquid"] and up[0].change == 30.0
    assert down == []


def bot_calls(database_url: str, send, rows, blocked_at: datetime | None = None,
              **settings) -> tuple[list[httpx.Request], list[PoeWatch]]:
    """Legt einen Nutzer mit `rows` an (Funktion Nutzer-ID → Zeilen), ruft `send` für poe1/Standard und
    gibt die Anfragen an die gefälschte Bot-API und die Merkliste danach zurück."""
    fake = FakeDiscord()
    seen: list[httpx.Request] = []
    fake.bot = lambda request: seen.append(request) or httpx.Response(200, json={"ok": True})
    config = Settings(**{"hub_secret_key": "test", "hub_guild_id": GUILD, **BOT, **settings})

    async def go() -> list[PoeWatch]:
        engine = create_async_engine(database_url)
        sessionmaker: async_sessionmaker[AsyncSession] = async_sessionmaker(engine, expire_on_commit=False)
        async with sessionmaker() as db:
            user = User(discord_id=4711, username="u", role="member", blocked_at=blocked_at)
            db.add(user)
            await db.flush()
            db.add_all(rows(user.id))
            await db.commit()
        async with httpx.AsyncClient(transport=httpx.MockTransport(fake)) as http:
            await send(sessionmaker, http, config, "poe1", LEAGUE)
        async with sessionmaker() as db:
            watches = list(await db.scalars(select(PoeWatch)))
        await engine.dispose()
        return watches

    return seen, asyncio.run(go())


def test_tell_bot_payload(database_url):
    seen, watches = bot_calls(database_url, send_alerts, lambda user_id: [item(), watch(user_id=user_id)])
    assert watches[0].ref_price == 125.0
    assert len(seen) == 1 and seen[0].method == "POST" and seen[0].url.path == "/control/poe/alert"
    assert seen[0].headers["authorization"] == f"Bearer {BOT['bot_control_key']}"
    body = json.loads(seen[0].content)
    assert body["guild_id"] == GUILD and body["discord_id"] == 4711 and body["change"] == 25.0


def test_no_alert_for_blocked_user(database_url):
    seen, _ = bot_calls(database_url, send_alerts, lambda user_id: [item(), watch(user_id=user_id)],
                        blocked_at=datetime.now(UTC))
    assert seen == []


def test_no_alert_without_guild(database_url):
    seen, watches = bot_calls(database_url, send_alerts, lambda user_id: [item(), watch(user_id=user_id)],
                              hub_guild_id=None)
    assert seen == [] and watches[0].ref_price == 100.0


def test_no_daily_without_guild(database_url):
    seen, _ = bot_calls(database_url, send_daily, lambda user_id: [item(key="b"), yesterday("b", 100.0)],
                        hub_guild_id=None)
    assert seen == []


def yesterday(key: str, price: float) -> PoePrice:
    day = datetime.now(TZ).date() - timedelta(days=1)
    return PoePrice(game="poe1", league=LEAGUE, key=key, day=day, price=price)


def test_send_daily(database_url):
    seen, _ = bot_calls(database_url, send_daily, lambda user_id: [item(key="a"), yesterday("a", 100.0)])
    assert len(seen) == 1 and seen[0].url.path == "/control/poe/daily"
    body = json.loads(seen[0].content)
    assert body["guild_id"] == GUILD and [m["key"] for m in body["up"]] == ["a"] and body["down"] == []


def test_send_daily_without_movers(database_url):
    # Preis wie gestern: keine Änderung, also keine Post
    seen, _ = bot_calls(database_url, send_daily, lambda user_id: [item(key="a"), yesterday("a", 125.0)])
    assert seen == []


def test_movers_top_n_sorted():
    today = [item(key=f"k{i}", price=100.0 + 10 * i) for i in range(-6, 7)]
    old = {f"k{i}": 100.0 for i in range(-6, 7)}
    up, down = movers(today, old, "poe1")
    assert [m.key for m in up] == ["k6", "k5", "k4", "k3", "k2"] and len(up) == TOP_N
    assert [m.key for m in down] == ["k-6", "k-5", "k-4", "k-3", "k-2"]
    assert [m.change for m in down] == [-60.0, -50.0, -40.0, -30.0, -20.0]


def test_daily_post_once_per_day():
    # ein zu früh geweckter Schlaf (17:59:59 in Berlin) nach der Post von heute wartet bis morgen
    early = datetime(2026, 11, 12, 16, 59, 59, tzinfo=UTC)
    assert seconds_until_daily_post(early, None) == 1
    assert seconds_until_daily_post(early, date(2026, 11, 12)) == 24 * 3600 + 1


def test_daily_post_time_across_dst():
    # Zeitumstellung in der Nacht zum 25.10.2026: 24.10. 19:30 Sommerzeit (17:30 UTC) bis 25.10. 18:00
    # Winterzeit (17:00 UTC) sind 23,5 Stunden, nicht 22,5
    assert seconds_until_daily_post(datetime(2026, 10, 24, 17, 30, tzinfo=UTC), None) == 23.5 * 3600
    assert seconds_until_daily_post(datetime(2026, 10, 25, 11, 0, tzinfo=UTC), None) == 6 * 3600
