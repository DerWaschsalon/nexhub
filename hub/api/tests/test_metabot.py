"""Würfeltabellen von MetaBot.GG lesen (metabot.py). Seiten nachgebaut (fake_metabot.py), Inhalte erfunden."""
import asyncio

import httpx

from nexhub_api import metabot

from .fake_metabot import BOW_DE, BOW_EN, FakeMetaBot, page


def test_adresse_aus_dem_namen():
    assert metabot.slug("Enraged Kromede Longbow") == "enraged-kromede-longbow"
    assert metabot.slug("Hunter's Ring") == "hunters-ring"


def test_wuerfe_und_skills():
    data = metabot.parse(BOW_EN)
    assert data["roll_count"] == 3
    assert data["rolls"][0] == {"name": "Mehrfachtreffer-Chance", "min": 7.9, "max": 9.1, "unit": "%", "chance": 6.0}
    assert data["rolls"][2]["unit"] == ""
    assert data["skills"]["Ranger"] == {"max_level": 1, "options": [{"name": "Zielpfeil", "chance": 50.0},
                                                                    {"name": "Orkanpfeil", "chance": 50.0}]}


def test_gleiche_chance_fuer_alle_skills():
    html = page([], {"Ranger": [("A", ""), ("B", "")]}, level=4).replace("2 skills", "2 skills · 50% each")
    skills = metabot.parse(html)["skills"]["Ranger"]
    assert skills["max_level"] == 4 and [o["chance"] for o in skills["options"]] == [50.0, 50.0]


def test_deutsche_namen_ueber_die_reihenfolge():
    data = metabot.merge(metabot.parse(BOW_EN), metabot.parse(BOW_DE))
    assert data["rolls"][0]["name_de"] == "Mehrfachtreffer"
    assert data["skills"]["ranger"]["options"][0]["name_de"] == "Zielpfeil"


def test_abruf_beide_sprachen_und_fehler():
    fake = FakeMetaBot()

    async def go(name: str) -> dict:
        async with httpx.AsyncClient(transport=httpx.MockTransport(fake)) as http:
            return await metabot.item(http, name)

    data = asyncio.run(go("Testbogen"))
    assert data["url"] == "https://metabot.gg/en/aion-2/items/testbogen"
    assert fake.calls == ["/en/aion-2/items/testbogen", "/de_DE/aion-2/items/testbogen"]
    try:
        asyncio.run(go("Gibt es nicht"))
    except metabot.MetaBotError as e:
        assert "nicht gefunden" in str(e)
    else:
        raise AssertionError("fehlender Gegenstand muss melden")
