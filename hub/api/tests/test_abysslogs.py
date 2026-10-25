"""Abyss-Logs-Rangliste und Auswahl der Vergleichsgruppe. API nachgebaut (fake_abyss.py)."""
import asyncio

import httpx
import pytest

from nexhub_api.abysslogs import AbyssError, abyss_class, leaderboard, pick_group, top_bosses

from .fake_abyss import FakeAbyss, entry


@pytest.fixture
def abyss() -> FakeAbyss:
    return FakeAbyss()


def run(abyss: FakeAbyss, work):
    async def go():
        async with httpx.AsyncClient(transport=httpx.MockTransport(abyss)) as http:
            return await work(http)
    return asyncio.run(go())


def test_auswahl():
    entries = [entry("A", cp=100_000, dps=90_000), entry("A", cp=100_000, dps=95_000),  # doppelt: bester zählt
               entry("B", cp=140_000, dps=99_000),                                     # zu stark
               entry("C", cp=110_000, dps=80_000, duration=0.01),                      # Müll
               entry("D", cp=90_000, dps=70_000)]
    group = pick_group(entries, own_cp=100_000)
    assert [x["playerName"] for x in group] == ["A", "D"]
    assert group[0]["dps"] == 95_000


def test_klasse():
    assert (abyss_class("ranger"), abyss_class("spiritmaster")) == ("Ranger", "Elementalist")


def test_bosse_und_rangliste(abyss):
    assert run(abyss, top_bosses) == [2350709, 2340601]
    rows = run(abyss, lambda http: leaderboard(http, "Ranger", 2350709))
    assert rows[0]["playerName"] == "Bogenheld"
    assert "class=Ranger" in abyss.last_query and "boss=2350709" in abyss.last_query and "region=eu" in abyss.last_query


@pytest.mark.parametrize("answer", [500, {"kaputt": True}])
def test_fehler_wird_abysserror(abyss, answer):
    abyss.routes["/v1/leaderboards"] = answer
    with pytest.raises(AbyssError):
        run(abyss, lambda http: leaderboard(http, "Ranger", 2350709))


def test_boss_ohne_rangliste_ist_leer(abyss):
    # Abyss Logs führt nicht für jeden Boss eine Rangliste
    abyss.routes["/v1/leaderboards"] = (400, {"error": "boss is not ranked"})
    assert run(abyss, lambda http: leaderboard(http, "Ranger", 2356708)) == []
