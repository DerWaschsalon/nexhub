"""Preisalarm und Tagespost für Path of Exile: Regeln ohne Netz, Versand über die gefälschte Bot-API."""
from __future__ import annotations

import asyncio
import json
from datetime import UTC, date, datetime

import httpx
from sqlalchemy import select
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from nexhub_api.config import Settings
from nexhub_api.main import seconds_until_daily_post
from nexhub_api.models import PoeItem, PoeWatch, User
from nexhub_api.poe_alerts import check_watch, movers, send_alerts

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


def test_tell_bot_payload(database_url):
    fake = FakeDiscord()
    seen: list[httpx.Request] = []
    fake.bot = lambda request: seen.append(request) or httpx.Response(200, json={"ok": True})
    settings = Settings(hub_secret_key="test", hub_guild_id=GUILD, **BOT)

    async def go() -> None:
        engine = create_async_engine(database_url)
        sessionmaker = async_sessionmaker(engine, expire_on_commit=False)
        async with sessionmaker() as db:
            user = User(discord_id=4711, username="u", role="member")
            db.add_all([user, item()])
            await db.flush()
            db.add(watch(user_id=user.id))
            await db.commit()
        async with httpx.AsyncClient(transport=httpx.MockTransport(fake)) as http:
            await send_alerts(sessionmaker, http, settings, "poe1", LEAGUE)
        async with sessionmaker() as db:
            assert (await db.scalars(select(PoeWatch))).one().ref_price == 125.0
        await engine.dispose()

    asyncio.run(go())
    assert len(seen) == 1 and seen[0].method == "POST" and seen[0].url.path == "/control/poe/alert"
    assert seen[0].headers["authorization"] == f"Bearer {BOT['bot_control_key']}"
    body = json.loads(seen[0].content)
    assert body["guild_id"] == GUILD and body["discord_id"] == 4711 and body["change"] == 25.0


def test_daily_post_time_across_dst():
    # Zeitumstellung in der Nacht zum 25.10.2026: 24.10. 19:30 Sommerzeit (17:30 UTC) bis 25.10. 18:00
    # Winterzeit (17:00 UTC) sind 23,5 Stunden, nicht 22,5
    assert seconds_until_daily_post(datetime(2026, 10, 24, 17, 30, tzinfo=UTC)) == 23.5 * 3600
    assert seconds_until_daily_post(datetime(2026, 10, 25, 11, 0, tzinfo=UTC)) == 6 * 3600
