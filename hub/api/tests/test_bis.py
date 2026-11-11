"""BiS-Listen: Sammler (bis_collector.py), Auswertung (bis_stats.py) und Route. Abyss Logs und NC nachgebaut
(fake_abyss.py, fake_nc.py), nur erfundene Daten."""
import asyncio
import json

import httpx
import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from nexhub_api import bis_collector
from nexhub_api.aion2 import NC
from nexhub_api.bis_collector import BisCollector, pool
from nexhub_api.bis_stats import aggregate
from nexhub_api.models import BisQueue
from nexhub_api.routes import bis as bis_route

from .conftest import MEMBER
from .fake_nc import search_row
from .test_armory import login

TOP = [f"Bogenheld{i}" for i in range(1, 6)]


@pytest.fixture(autouse=True)
def small(monkeypatch):
    """Fünf statt 200 Spieler je Klasse, ab drei gibt es Prozente."""
    monkeypatch.setattr(bis_collector, "POOL_SIZE", 5)
    monkeypatch.setattr(bis_route, "MIN_SAMPLE", 3)


def with_top_rangers(fake):
    """Die Rangliste nennt die fünf Bogenhelden, die NC-Suche findet sie als Waldläufer (pcId 13)."""
    fake.nc.rows = [search_row(n, cid=f"{n}%3D", pc=13) for n in TOP]


def run(database_url, fake, work):
    async def go():
        engine = create_async_engine(database_url)
        sessionmaker = async_sessionmaker(engine, expire_on_commit=False)
        async with httpx.AsyncClient(transport=httpx.MockTransport(fake)) as http:
            result = await work(BisCollector(sessionmaker, NC(http, 0), http), sessionmaker)
        await engine.dispose()
        return result
    return asyncio.run(go())


async def collect_all(collector: BisCollector) -> None:
    """Takte, bis die Warteschlange leer ist."""
    await collector.tick()
    while await collector._next():
        await collector.tick()


def test_sammler_fuellt_bestand_ohne_namen(fake, database_url):
    with_top_rangers(fake)

    async def work(collector, sessionmaker):
        await collect_all(collector)
        async with sessionmaker() as db:
            return await pool(db, "ranger"), (await db.scalars(select(BisQueue))).all()

    samples, queue = run(database_url, fake, work)
    assert len(samples) == 5 and queue == []
    assert {s.raid for s in samples} == {"Altboss"} and {s.tier for s in samples} == {"Hard"}
    assert len({s.character_key for s in samples}) == 5
    assert set(samples[0].data) == {"v", "de", "en"}
    assert samples[0].data["en"]["equipment"][0]["detail"]["sub"][0]["name"] == "Mehrfachtreffer-Chance"
    assert "Bogenheld" not in json.dumps([s.data for s in samples])  # keine Namen im Bestand


def test_voller_bestand_ersetzt_den_aeltesten_ohne_doppel(fake, database_url, monkeypatch):
    with_top_rangers(fake)
    monkeypatch.setattr(bis_collector, "POOL_SIZE", 3)

    async def work(collector, sessionmaker):
        await collect_all(collector)
        await collect_all(collector)  # zweiter Durchlauf: dieselben drei werden aktualisiert
        async with sessionmaker() as db:
            return await pool(db, "ranger")

    assert len(run(database_url, fake, work)) == 3


def test_nc_fehler_dreimal_versuchen(fake, database_url):
    with_top_rangers(fake)
    fake.nc.routes["/api/character/equipment"] = 500

    async def work(collector, sessionmaker):
        await collector.refill()
        async with sessionmaker() as db:
            row = await db.scalar(select(BisQueue).where(BisQueue.cls == "ranger").limit(1))
        tries = []
        for _ in range(3):
            await collector.collect(row)
            async with sessionmaker() as db:
                left = await db.get(BisQueue, row.id)
            tries.append(left.tries if left else None)
        return tries

    assert run(database_url, fake, work) == [1, 2, None]


def item(name: str, enchant: int, sub: list[tuple[str, str]], stones: list[str]) -> dict:
    return {"slot_name": "MainHand", "name": name, "icon": None, "grade": "Unique", "enchant": enchant, "exceed": 0,
            "detail": {"level": 86, "category": "Bogen", "max_enchant": 15, "main": [],
                       "sub": [{"name": n, "value": v} for n, v in sub],
                       "stones": [{"name": s, "value": "+6", "grade": "Legend", "icon": None} for s in stones],
                       "godstones": [], "skills": []}}


def test_auswertung_anteile_je_platz_und_skill():
    samples = [
        {"equipment": [item("Bogen A", 15, [("Krit", "50"), ("Tempo", "10%")], ["Krit", "Krit"])],
         "skills": [{"name": "Zielpfeil", "category": "Active", "level": 17, "learned": True, "equipped": True},
                    {"name": "Ruhe", "category": "Passive", "level": 5, "learned": True, "equipped": False}]},
        {"equipment": [item("Bogen A", 13, [("Krit", "40")], ["LP"])],
         "skills": [{"name": "Zielpfeil", "category": "Active", "level": 15, "learned": True, "equipped": False}]},
        {"equipment": [item("Bogen B", 15, [("Krit", "60"), ("Tempo", "8%")], [])], "skills": []},
        {"equipment": [], "skills": []},
    ]
    result = aggregate(samples)
    slot = result["slots"][0]
    assert slot["players"] == 3 and slot["share"] == 0.75
    assert slot["item"]["name"] == "Bogen A" and slot["item"]["enchant"] == 15
    assert slot["max_enchant"] == pytest.approx(2 / 3)
    assert [(i["name"], round(i["share"], 2)) for i in slot["items"]] == [("Bogen A", 0.67), ("Bogen B", 0.33)]
    lines = {(line["kind"], line["name"]): line for line in slot["lines"]}
    assert lines[("stat", "Krit")]["share"] == 1.0 and lines[("stat", "Krit")]["value"] == 50
    assert lines[("stat", "Tempo")]["share"] == 0.667 and lines[("stat", "Tempo")]["unit"] == "%"
    assert lines[("stone", "Krit")]["share"] == 0.333  # doppelt auf einem Teil zählt einmal
    assert slot["item"]["detail"]["sub"] == [{"name": "Krit", "value": "50"}, {"name": "Tempo", "value": "9%"}]
    # aktive zählen angelegt, passive gelernt; Anteil über alle vier Spieler
    skills = {s["name"]: (s["share"], s["level"]) for s in result["skills"]}
    assert skills == {"Zielpfeil": (0.25, 17), "Ruhe": (0.25, 5)}


def test_route_zeigt_klassen_und_auswertung(make_client, fake, database_url):
    with_top_rangers(fake)
    run(database_url, fake, lambda collector, _: collect_all(collector))
    c = login(make_client, fake, MEMBER)

    assert [(k["cls"], k["size"], k["hard"]) for k in c.get("/api/bis").json()] == [("ranger", 5, 5)]
    d = c.get("/api/bis/ranger", params={"lang": "de"}).json()
    assert (d["size"], d["tiers"], d["raid"]) == (5, {"Hard": 5}, "Altboss")
    slot = d["slots"][0]
    assert slot["item"]["name"] == "Testbogen" and slot["item"]["enchant"] == 15
    assert {"kind": "stat", "name": "Mehrfachtreffer-Chance", "value": 9.1, "unit": "%", "max": 9.1,
            "share": 1.0} in slot["lines"]
    assert [s["name"] for s in d["skills"]] == ["Zielpfeil"]  # das Stigma ist angelegt, aber nicht gelernt

    assert c.get("/api/bis/ranger", params={"tier": "Normal"}).json()["slots"] == []  # zu wenige
    assert c.get("/api/bis/unbekannt").status_code == 404
