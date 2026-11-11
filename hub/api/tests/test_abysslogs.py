"""Top-Spieler aus den Ranglisten von Abyss Logs (abysslogs.py). API nachgebaut (fake_abyss.py)."""
import asyncio

import httpx

from nexhub_api.abysslogs import best_per_name, raids, top_players

from .fake_abyss import FakeAbyss, entry


def run(fake: FakeAbyss, work):
    async def go():
        async with httpx.AsyncClient(transport=httpx.MockTransport(fake)) as http:
            return await work(http)
    return asyncio.run(go())


def test_raids_neueste_zuerst_hard_vor_normal():
    found = run(FakeAbyss(), raids)
    assert [(name, tier) for name, tier, _ in found] == [("Neuboss", "Hard"), ("Neuboss", "Normal"),
                                                          ("Altboss", "Hard"), ("Altboss", "Normal")]


def test_neuester_raid_mit_genug_eintraegen():
    fake = FakeAbyss()
    label, players = run(fake, lambda http: top_players(http, "ranger", 5))
    assert label == "Altboss · Hard"
    assert [p["playerName"] for p in players] == [f"Bogenheld{i}" for i in range(1, 6)]
    # ohne genug Einträge im Hard der Normal-Modus desselben Raids
    fake.boards = {8002: [f"Normalheld{i}" for i in range(5)]}
    assert run(fake, lambda http: top_players(http, "ranger", 5))[0] == "Altboss · Normal"


def test_je_name_der_beste_echte_kampf():
    rows = [entry("A", 100), entry("A", 300), entry("B", 200), entry("C", 999, duration=5)]
    assert [(e["playerName"], e["dps"]) for e in best_per_name(rows)] == [("A", 300), ("B", 200)]
