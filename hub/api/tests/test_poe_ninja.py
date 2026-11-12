"""Preise von poe.ninja: Umwandeln der Antworten, ETag, Speichern, Liga und Fehler einzelner Kategorien."""
from __future__ import annotations

import asyncio
import copy
import time
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from datetime import datetime
from zoneinfo import ZoneInfo

import httpx
from sqlalchemy import select
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from nexhub_api.config import Settings
from nexhub_api.models import PoeItem, PoePrice
from nexhub_api.poe_ninja import (EXCHANGE_TYPES, GAMES, STASH_TYPES, PoeNinja, ninja_url, parse_exchange,
                                  parse_stash)
from nexhub_api.poe_prices import PoePrices

from .fake_poe_ninja import FakePoeNinja, sample

LEAGUE2 = "Runes of Aldur"  # erste Liga in data/poe_ninja/poe2_leagues.json


def ninja(fake: FakePoeNinja) -> PoeNinja:
    return PoeNinja(httpx.AsyncClient(transport=httpx.MockTransport(fake)), "NexHub/test (+https://example.org)")


@asynccontextmanager
async def prices(database_url: str, fake: FakePoeNinja, **settings: str) -> AsyncIterator[PoePrices]:
    engine = create_async_engine(database_url)
    try:
        yield PoePrices(async_sessionmaker(engine, expire_on_commit=False), ninja(fake),
                        Settings(hub_secret_key="test", **settings))
    finally:
        await engine.dispose()


async def items(service: PoePrices) -> dict[str, PoeItem]:
    async with service.sessionmaker() as db:
        return {row.key: row for row in await db.scalars(select(PoeItem))}


def test_parse_exchange_poe2():
    lines = parse_exchange("poe2", LEAGUE2, "Currency", sample("poe2_exchange_Currency"))
    alch = next(line for line in lines if line.key == "orb-of-alchemy")
    assert (alch.name, alch.unit, alch.price, alch.trade_volume) == ("Orb of Alchemy", "divine", 0.005, 1.33)
    assert (alch.game, alch.league, alch.category, alch.listings) == ("poe2", LEAGUE2, "Currency", None)
    assert alch.icon and alch.icon.startswith("https://poe.ninja/gen/image/")


def test_parse_stash_poe1():
    lines = parse_stash("poe1", "Standard", "UniqueWeapon", sample("poe1_stash_UniqueWeapon"))
    staff = next(line for line in lines if line.key == "the-searing-touch-long-staff")
    assert (staff.name, staff.unit, staff.price, staff.listings) == ("The Searing Touch", "chaos", 5890980, 30)
    assert staff.icon and staff.icon.startswith("https://web.poecdn.com/")


def test_parse_stash_poe2_unit():
    data = sample("poe2_stash_UniqueWeapons")
    lines = parse_stash("poe2", LEAGUE2, "UniqueWeapons", data)
    bite = next(line for line in lines if line.key == "winters-bite-glass-shank")
    assert bite.unit == data["core"]["primary"] == "divine"
    assert (bite.name, bite.price, bite.listings) == ("Winter's Bite", 3470, 10)


def test_ninja_url():
    # Pfade auf der Website am 12.11.2026 nachgesehen
    assert (ninja_url("poe1", "Standard", "UniqueWeapon", "the-searing-touch-long-staff")
            == "https://poe.ninja/poe1/economy/standard/unique-weapons/the-searing-touch-long-staff")
    assert (ninja_url("poe2", "HC Runes of Aldur", "Breach", "x")
            == "https://poe.ninja/poe2/economy/runesofaldurhc/breach-catalyst/x")


def test_overview_uses_etag():
    fake = FakePoeNinja()

    async def go():
        client = ninja(fake)
        first = await client.overview("poe2", "exchange", LEAGUE2, "Currency")
        second = await client.overview("poe2", "exchange", LEAGUE2, "Currency")
        return first, second
    first, second = asyncio.run(go())
    assert first == second == sample("poe2_exchange_Currency")
    assert "if-none-match" not in fake.requests[0].headers
    assert fake.requests[1].headers["if-none-match"].startswith('W/"')  # Fake antwortet darauf mit 304
    assert fake.requests[1].url.params["league"] == LEAGUE2


def test_refresh_keeps_missing_item(database_url):
    fake = FakePoeNinja()
    currency = copy.deepcopy(fake.overviews["poe2/exchange/Currency"])

    async def go():
        async with prices(database_url, fake) as service:
            assert await service.refresh("poe2") == LEAGUE2
            before = await items(service)
            # zweiter Abruf: Chaos Orb fehlt, Alchemy hat einen neuen Preis
            currency["lines"] = [line for line in currency["lines"] if line["id"] != "chaos"]
            currency["lines"][0]["primaryValue"] = 0.007
            fake.overviews["poe2/exchange/Currency"] = currency
            await service.refresh("poe2")
            after = await items(service)
            async with service.sessionmaker() as db:
                days = list(await db.scalars(select(PoePrice).where(PoePrice.key == "orb-of-alchemy")))
            return before, after, days
    before, after, days = asyncio.run(go())
    assert {"chaos-orb", "orb-of-alchemy", "winters-bite-glass-shank"} <= before.keys()
    assert after["chaos-orb"].price == before["chaos-orb"].price
    assert after["chaos-orb"].updated_at == before["chaos-orb"].updated_at
    assert after["orb-of-alchemy"].price == 0.007
    assert [(d.league, d.day, d.price) for d in days] == [(LEAGUE2, datetime.now(ZoneInfo("Europe/Berlin")).date(),
                                                           0.007)]


def test_refresh_survives_broken_category(database_url):
    fake = FakePoeNinja()
    weapons = fake.overviews["poe2/stash/UniqueWeapons"]
    armour = copy.deepcopy(weapons)
    armour["lines"] = [{**armour["lines"][0], "detailsId": "test-armour", "name": "Testrüstung", "primaryValue": 7}]
    broken = copy.deepcopy(weapons)
    broken["lines"][0]["primaryValue"] = 1  # gültige Zeile vor der kaputten wird auch nicht gespeichert
    broken["lines"].append({"unbekannt": True})

    async def go():
        async with prices(database_url, fake) as service:
            await service.refresh("poe2")
            fake.overviews.update({"poe2/exchange/Currency": 500, "poe2/stash/UniqueWeapons": broken,
                                   "poe2/stash/UniqueArmours": armour})
            await service.refresh("poe2")
            return await items(service)
    rows = asyncio.run(go())
    assert rows["test-armour"].price == 7 and rows["test-armour"].category == "UniqueArmours"
    assert rows["orb-of-alchemy"].price == 0.005
    assert rows["winters-bite-glass-shank"].price == 3470


def test_league_setting_wins(database_url):
    fake = FakePoeNinja()

    async def go():
        async with prices(database_url, fake, hub_poe1_league="Standard") as service:
            fixed = await service.league("poe1")
            assert fake.requests == []
            return fixed, await service.league("poe2")
    assert asyncio.run(go()) == ("Standard", LEAGUE2)


def test_user_agent(make_client, fake):
    """Der Hintergrundauftrag läuft nur mit hub_poe_enabled; jede Anfrage nennt den Hub."""
    with make_client() as c:
        assert c.app.state.poe_prices is None
    assert fake.poe_ninja.requests == []
    expected = sum(1 + len(EXCHANGE_TYPES[game]) + len(STASH_TYPES[game]) for game in GAMES)
    with make_client(hub_poe_enabled=True) as c:
        assert c.app.state.poe_prices is not None
        deadline = time.monotonic() + 10
        while len(fake.poe_ninja.requests) < expected and time.monotonic() < deadline:
            time.sleep(0.05)
    assert len(fake.poe_ninja.requests) == expected
    assert all(r.headers["user-agent"].startswith("NexHub/") for r in fake.poe_ninja.requests)
