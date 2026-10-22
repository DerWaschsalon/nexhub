"""Client für die AION-2-Website gegen die nachgebaute Seite (fake_nc.py)."""
import asyncio
import os

import httpx
import pytest

from nexhub_api.aion2 import NC, NCError, NotFound, combat_power, item_level, localized, shard_of

from .fake_nc import ICON, FakeNC, search_row


def client(fake) -> NC:
    return NC(httpx.AsyncClient(transport=httpx.MockTransport(fake)), pause=0)


def run(coro):
    return asyncio.run(coro)


def test_shard_aus_server_id():
    assert shard_of(1301) == shard_of(2323) == "eu"
    assert shard_of(1101) == "nae" and shard_of(2205) == "naw" and shard_of(1401) == "la" and shard_of(2510) == "as"
    assert shard_of(1001) is None and shard_of(0) is None and shard_of(99999) is None


def test_findet_genau_den_namen_auf_dem_server():
    fake = FakeNC()
    fake.rows = [search_row("Testheldin", cid="zzz"), search_row("Testheld", cid="abc%3D")]
    assert run(client(fake).find("testheld", 2302)) == "abc="


def test_nicht_gefunden():
    fake = FakeNC()
    with pytest.raises(NotFound):
        run(client(fake).find("Niemand", 2302))
    fake.rows = [search_row("Testheld", server=2301)]
    with pytest.raises(NotFound):
        run(client(fake).find("Testheld", 2302))


def test_server_nicht_unterstuetzt_fragt_nc_nicht():
    fake = FakeNC()
    with pytest.raises(NotFound, match="Server nicht unterstützt"):
        run(client(fake).find("Testheld", 1001))
    with pytest.raises(NotFound, match="Server unbekannt"):
        run(client(fake).find("Testheld", 0))
    assert fake.calls == []


def test_momentaufnahme():
    fake = FakeNC()
    data = run(client(fake).snapshot(2302, "abc="))
    assert data["profile"] == {"name": "Testheld", "level": 45, "class": "Waldläufer", "gender": "Weiblich",
                               "race": 2, "server": "Zikel", "guild": "Testgilde", "title": "Füttere mich!",
                               "combat_power": 123456,
                               "image": "https://profileimg.plaync.com/game_profile_images/aion2global/images?charKey=1"}
    assert data["stats"][0] == {"type": "STR", "name": "Macht", "value": 36, "effects": ["Angriffskraft + +3.6%"]}
    assert data["stats"][1]["effects"] == []
    assert item_level(data) == 2554
    assert data["titles"] == {"owned": 206, "total": 297, "equipped": [
        {"name": "Goldener Glanz", "grade": "Unique", "category": "Attack", "effects": ["Krit.-Angriffskraft +45"]}]}
    assert data["equipment"] == [{"id": 110430050, "slot": 1, "slot_name": "MainHand", "name": "Testbogen",
                                  "grade": "Unique", "enchant": 15, "exceed": 1, "icon": ICON}]
    assert data["pet"]["name"] == "Testeule" and data["wing"]["name"] == "Testflügel"
    assert data["skills"][1] == {"name": "Greifenpfeil", "category": "Dp", "level": 0, "learned": False,
                                 "equipped": True, "icon": ICON}
    nezekan, azphel = data["daevanion"]
    assert nezekan == {"id": 31, "name": "Nezekan",
                       "icon": "https://assets.playnccdn.com/static-aion2-gamedata/resources/UT_Sword.png",
                       "open": True, "open_nodes": 64, "total_nodes": 88, "stats": ["LP +600"],
                       "skills": ["Orkanpfeil +1"],
                       # leere Felder (type None) fallen weg, leere Effekte auch
                       "nodes": [{"row": 8, "col": 8, "type": "Start", "grade": "None", "open": False,
                                  "effects": []},
                                 {"row": 3, "col": 7, "type": "SkillLevel", "grade": "Rare", "open": True,
                                  "effects": ["Orkanpfeil +1"]},
                                 {"row": 3, "col": 8, "type": "Stat", "grade": "Common", "open": False,
                                  "effects": ["LP +600"]}]}
    assert azphel["open"] is False and azphel["stats"] == [] and azphel["icon"] is None and azphel["nodes"] == []
    # geschlossenes Brett wird nicht abgefragt
    assert fake.calls.count("/api/character/daevanion/detail") == 1


def test_unbekannter_charakter_bei_info():
    fake = FakeNC()
    fake.routes["/api/character/info"] = {"profile": {"characterId": ""}}
    with pytest.raises(NotFound):
        run(client(fake).snapshot(2302, "abc="))


def test_format_unbekannt():
    fake = FakeNC()
    fake.routes["/aion2global/search/v2/character"] = {"items": []}
    with pytest.raises(NCError, match="Format unbekannt"):
        run(client(fake).find("Testheld", 2302))
    fake.routes["/api/character/info"] = {"etwas": 1}
    with pytest.raises(NCError, match="Format unbekannt"):
        run(client(fake).snapshot(2302, "abc="))


def test_wiederholt_bei_5xx_und_netzfehlern():
    fake = FakeNC()
    answers: list[object] = [503, httpx.ConnectError("weg")]

    def flaky(request: httpx.Request) -> httpx.Response:
        if answers:
            a = answers.pop(0)
            if isinstance(a, Exception):
                raise a
            return httpx.Response(a)
        return fake(request)

    assert run(client(flaky).find("Testheld", 2302)) == "abc="


def test_gibt_nach_drei_versuchen_auf():
    fake = FakeNC()
    fake.routes["/aion2global/search/v2/character"] = 502
    with pytest.raises(NCError, match="HTTP 502"):
        run(client(fake).find("Testheld", 2302))
    assert fake.calls.count("/aion2global/search/v2/character") == 3


def test_4xx_ohne_wiederholung():
    fake = FakeNC()
    fake.routes["/aion2global/search/v2/character"] = 403
    with pytest.raises(NCError, match="HTTP 403"):
        run(client(fake).find("Testheld", 2302))
    assert len(fake.calls) == 1


@pytest.mark.skipif(not os.environ.get("AION2_LIVE"), reason="nur mit AION2_LIVE=1 gegen die echte Seite")
def test_echte_seite():
    """Prüft nur das Format, nicht die Inhalte. Name und Server aus der Umgebung, damit nichts Echtes im Repo
    steht: AION2_LIVE=1 AION2_NAME=<Charakter> AION2_SERVER=<Server-ID> uv run pytest -q tests/test_aion2.py -k echte"""
    async def go() -> dict:
        async with httpx.AsyncClient() as http:
            nc = NC(http)
            server = int(os.environ["AION2_SERVER"])
            return await nc.snapshot(server, await nc.find(os.environ["AION2_NAME"], server), "de", items=True)

    data = run(go())
    assert data["profile"]["name"] and data["equipment"] and data["skills"] and data["daevanion"]
    assert any(i["detail"] and i["detail"]["main"] for i in data["equipment"])


def test_beide_sprachen_und_werte_je_gegenstand():
    fake = FakeNC()
    data = run(client(fake).snapshots(2302, "abc=", items=True))
    assert data["v"] == 2 and set(data) == {"v", "de", "en"}
    assert {"de-DE", "en-US"} <= set(fake.langs)
    assert item_level(data) == 2554 and combat_power(data) == 123456
    detail = data["de"]["equipment"][0]["detail"]
    assert detail["main"] == [{"name": "Angriffskraft", "value": "486", "extra": "146"}]
    assert detail["sub"] == [{"name": "Mehrfachtreffer-Chance", "value": "9.1%"}]
    assert detail["stones"][0] == {"name": "Kritischer Treffer", "value": "+6", "grade": "Legend", "icon": ICON}
    assert detail["godstones"][0]["desc"] == "10 % Chance auf Wind-Schaden"
    assert detail["skills"] == [{"name": "Zielpfeil", "level": 2, "icon": ICON}]
    assert detail["set"] == {"name": "Testset", "equipped": 3, "total": 5,
                             "bonuses": [{"degree": 2, "lines": ["Angriffskraft (PvE) +60"]}]}
    # ohne items keine Anfrage je Gegenstand
    fake.calls.clear()
    run(client(fake).snapshots(2302, "abc="))
    assert "/api/character/equipment/item" not in fake.calls


def test_gegenstand_nicht_mehr_angelegt():
    fake = FakeNC()
    fake.routes["/api/character/equipment/item"] = 404  # so antwortet NC bei falschem Slot oder Gegenstand
    assert run(client(fake).item(2302, "abc=", "de", {"id": 1, "slot": 1, "enchant": 0})) is None
    assert run(client(fake).item(2302, "abc=", "de", {"id": None, "slot": 1})) is None


def test_alte_momentaufnahme_ohne_sprachen():
    old = {"profile": {"combat_power": 5}, "stats": [{"type": "ItemLevel", "value": 7}]}
    assert localized(old, "de") is old and combat_power(old) == 5 and item_level(old) == 7
