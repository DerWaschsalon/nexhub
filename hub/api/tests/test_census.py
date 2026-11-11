"""Zählung der Top-Spieler aus dem Bestand der BiS-Listen (census.py) und Bewertung in der Armory.
Abyss Logs, NC und MetaBot nachgebaut (fake_abyss.py, fake_nc.py, fake_metabot.py), nur erfundene Daten."""
import asyncio
import json

import httpx
import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from nexhub_api import bis_collector
from nexhub_api import census as census_module
from nexhub_api.census import Census
from nexhub_api.models import ClassCensus, ItemRolls

from .conftest import MEMBER
from .test_armory import NEW, login
from .test_bis import collect_all, with_top_rangers
from .test_bis import run as run_collector
from .test_devices import ORIGIN


@pytest.fixture(autouse=True)
def small(monkeypatch):
    """Ab fünf Spielern im Bestand zählen, ohne Pause zwischen den MetaBot-Seiten."""
    monkeypatch.setattr(census_module, "MIN_SAMPLE", 5)
    monkeypatch.setattr(bis_collector, "POOL_SIZE", 5)
    monkeypatch.setattr(census_module, "METABOT_PAUSE", 0)


def run(database_url, fake, work):
    async def go():
        engine = create_async_engine(database_url)
        sessionmaker = async_sessionmaker(engine, expire_on_commit=False)
        async with httpx.AsyncClient(transport=httpx.MockTransport(fake)) as http:
            result = await work(Census(sessionmaker, http), sessionmaker)
        await engine.dispose()
        return result
    return asyncio.run(go())


def test_zaehlung_aus_dem_bestand_der_bis_listen(make_client, fake, database_url):
    c = login(make_client, fake, MEMBER)
    cid = c.post("/api/armory", json=NEW, headers=ORIGIN).json()["id"]
    with_top_rangers(fake)
    run_collector(database_url, fake, lambda collector, _: collect_all(collector))

    async def work(census: Census, sessionmaker):
        due = await census.due()
        await census.count("ranger")
        async with sessionmaker() as db:
            row = await db.get(ClassCensus, "ranger")
            rolls = (await db.scalars(select(ItemRolls))).all()
        return due, row, rolls, await census.due()

    due, row, rolls, due_after = run(database_url, fake, work)
    assert due == ["ranger"] and due_after == []
    assert row.group_label == "EU · Altboss · Hard 5"
    assert row.data["slots"]["MainHand"]["players"] == 5
    assert row.data["slots"]["MainHand"]["lines"]["Mehrfachtreffer-Chance"] == 5
    assert row.data["tops"]["MainHand"]["Mehrfachtreffer-Chance"] == 9.1
    assert "Bogenheld" not in json.dumps(row.data)  # keine Namen der Top-Spieler
    assert [r.name for r in rolls] == ["Testbogen"]

    # Die Armory zeigt die Bewertung in beiden Sprachen
    d = c.get(f"/api/armory/{cid}").json()
    item = d["ratings"]["de"]["items"][0]
    assert (item["slot"], item["letter"], item["upgrade"]) == ("MainHand", "BiS", None)
    assert item["lines"][0]["max"] == 9.1 and item["lines"][0]["share"] == 1.0
    assert item["source"] == "https://metabot.gg/en/aion-2/items/testbogen"
    assert d["ratings"]["de"]["group"] == "EU · Altboss · Hard 5"


def test_wuerfeltabellen_nur_einmal_pro_woche(make_client, fake, database_url):
    async def work(census: Census, _):
        await census.load_rolls({"Testbogen", "Gibt es nicht"})
        before = len(fake.metabot.calls)
        await census.load_rolls({"Testbogen", "Gibt es nicht"})
        return before, len(fake.metabot.calls)

    before, after = run(database_url, fake, work)
    assert before == 3  # Testbogen englisch und deutsch, der unbekannte einmal (404)
    assert after == before


def test_ohne_zaehlung_keine_bewertung(make_client, fake):
    c = login(make_client, fake, MEMBER)
    cid = c.post("/api/armory", json=NEW, headers=ORIGIN).json()["id"]
    assert c.get(f"/api/armory/{cid}").json()["ratings"] == {}
