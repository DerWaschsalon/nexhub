"""Armory: Charaktere eintragen, abrufen, Verlauf, Rechte. NC ist nachgebaut (fake_nc.py), nur erfundene Daten."""
import asyncio
from datetime import UTC, datetime, timedelta

import httpx
from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from nexhub_api.aion2 import NC
from nexhub_api.armory import Armory
from nexhub_api.models import Character, CharacterDay

from .conftest import ADMIN, MEMBER, log_in
from .fake_nc import info, search_row
from .test_characters import with_servers
from .test_devices import ORIGIN, pair
from .test_runs import nexlog, upload

ON = {"hub_aion2_enabled": True}
NEW = {"name": "Testheld", "server_id": 2302, "character_id": "abc="}


def login(make_client, fake, who, **settings):
    c = make_client(**{**ON, **settings})
    c.__enter__()
    fake.user = who
    log_in(c)
    return c


def db_run(database_url, work):
    async def go():
        engine = create_async_engine(database_url)
        async with async_sessionmaker(engine, expire_on_commit=False)() as db:
            result = await work(db)
            await db.commit()
        await engine.dispose()
        return result
    return asyncio.run(go())


def age(database_url, character_id, hours):
    """Letzten Abruf zurückdatieren (Sperre des Knopfs, täglicher Lauf)."""
    when = datetime.now(UTC) - timedelta(hours=hours)
    db_run(database_url, lambda db: db.execute(update(Character).where(Character.id == character_id)
                                               .values(fetched_at=when)))


def test_suche(make_client, fake):
    fake.nc.rows = [search_row("Testheld"), search_row("Testheldin", cid="xyz%3D"),
                    search_row("Testheld", server=9999, cid="fremd%3D")]  # Server ohne Shard fällt weg
    c = login(make_client, fake, MEMBER)
    hits = c.get("/api/armory/search", params={"name": "testheld"}).json()
    assert [(h["name"], h["server_id"], h["character_id"], h["taken_by"]) for h in hits] == [
        ("Testheld", 2302, "abc=", None), ("Testheldin", 2302, "xyz=", None)]
    assert hits[0]["image"].startswith("https://profileimg.plaync.com/game_profile_images/")
    assert c.get("/api/armory/search", params={"name": "t"}).status_code == 422
    assert c.get("/api/armory/search", params={"name": "Testheld", "region": "kr"}).status_code == 422


def test_ausgeschaltet(make_client, fake):
    c = login(make_client, fake, MEMBER, hub_aion2_enabled=False)
    assert c.get("/api/armory/search", params={"name": "Testheld"}).status_code == 503
    assert c.post("/api/armory", json=NEW, headers=ORIGIN).status_code == 503
    assert c.get("/api/armory").json() == []


def test_eintragen_abrufen_verlauf(make_client, fake, database_url):
    c = login(make_client, fake, MEMBER)
    r = c.post("/api/armory", json=NEW, headers=ORIGIN)
    assert r.status_code == 201, r.text
    cid = r.json()["id"]
    # Der Abruf läuft im Hintergrund, im TestClient direkt nach der Antwort
    d = c.get(f"/api/armory/{cid}").json()
    assert (d["status"], d["combat_power"], d["item_level"], d["class_name"]) == ("ok", 123456, 2554, "Waldläufer")
    assert d["data"]["equipment"][0]["name"] == "Testbogen" and d["mine"] and d["can_delete"]
    assert [(x["combat_power"], x["item_level"]) for x in d["days"]] == [(123456, 2554)]
    # Mit bekannter Charakter-ID keine Suche, nur Profil, Ausrüstung, Daevanion
    assert "/aion2global/search/v2/character" not in fake.nc.calls

    listed = c.get("/api/armory").json()
    assert [(x["name"], x["owner"], x["mine"], x["class_name"], x["server"]) for x in listed] == [
        ("Testheld", "Testname", True, "Waldläufer", "Zikel")]
    assert listed[0]["image"].startswith("https://profileimg.plaync.com/")
    assert "data" not in listed[0]


def test_knopf_sperre_und_ein_eintrag_je_tag(make_client, fake, database_url):
    c = login(make_client, fake, MEMBER)
    cid = c.post("/api/armory", json=NEW, headers=ORIGIN).json()["id"]
    assert c.post(f"/api/armory/{cid}/refresh", headers=ORIGIN).status_code == 429
    age(database_url, cid, hours=1)
    stronger = info()
    stronger["profile"]["combatPower"] = 130000
    fake.nc.routes["/api/character/info"] = stronger
    assert c.post(f"/api/armory/{cid}/refresh", headers=ORIGIN).status_code == 202
    d = c.get(f"/api/armory/{cid}").json()
    assert d["combat_power"] == 130000
    assert [x["combat_power"] for x in d["days"]] == [130000]  # derselbe Tag wird überschrieben


def test_fehler_behaelt_die_letzten_daten(make_client, fake, database_url):
    c = login(make_client, fake, MEMBER)
    cid = c.post("/api/armory", json=NEW, headers=ORIGIN).json()["id"]
    age(database_url, cid, hours=1)
    fake.nc.routes["/api/character/info"] = 500
    assert c.post(f"/api/armory/{cid}/refresh", headers=ORIGIN).status_code == 202
    d = c.get(f"/api/armory/{cid}").json()
    assert d["status"] == "fehler" and d["error"]
    assert d["data"]["profile"]["combat_power"] == 123456 and len(d["days"]) == 1


def test_einmal_je_charakter_und_rechte(make_client, fake, database_url):
    member = login(make_client, fake, MEMBER)
    cid = member.post("/api/armory", json=NEW, headers=ORIGIN).json()["id"]
    admin = login(make_client, fake, ADMIN)
    r = admin.post("/api/armory", json=NEW, headers=ORIGIN)
    assert r.status_code == 409 and "Testname" in r.json()["detail"]
    hits = admin.get("/api/armory/search", params={"name": "Testheld"}).json()
    assert hits[0]["taken_by"] == "Testname"
    assert admin.post("/api/armory", json={**NEW, "server_id": 9999}, headers=ORIGIN).status_code == 422

    # Alle sehen alles; austragen darf nur, wer eingetragen hat, oder ein Admin
    d = admin.get(f"/api/armory/{cid}").json()
    assert not d["mine"] and d["can_delete"]
    fake.roles[444] = fake.roles[MEMBER]
    other = login(make_client, fake, 444)
    assert other.get(f"/api/armory/{cid}").json()["can_delete"] is False
    assert other.delete(f"/api/armory/{cid}", headers=ORIGIN).status_code == 403
    assert admin.delete(f"/api/armory/{cid}", headers=ORIGIN).status_code == 204
    assert member.get(f"/api/armory/{cid}").status_code == 404
    assert db_run(database_url, lambda db: db.scalars(select(CharacterDay))).all() == []


def test_hoechstens_zwanzig(make_client, fake):
    c = login(make_client, fake, MEMBER)
    for i in range(20):
        assert c.post("/api/armory", json={**NEW, "character_id": f"c{i}"}, headers=ORIGIN).status_code == 201
    assert c.post("/api/armory", json={**NEW, "character_id": "c20"}, headers=ORIGIN).status_code == 422


def test_run_spieler_verlinkt_die_armory(make_client, fake, as_user):
    member = login(make_client, fake, MEMBER)
    cid = member.post("/api/armory", json=NEW, headers=ORIGIN).json()["id"]
    with make_client(**ON) as c:
        token = pair(c, as_user(MEMBER))
        run_id = upload(c, token, with_servers(nexlog(), {"Testheld": 2302})).json()["id"]
    found = {x["name"]: x["armory_id"] for x in member.get(f"/api/runs/{run_id}/characters").json()}
    assert found == {"Moonlin": None, "Testheld": cid}
    held = next(x for x in member.get(f"/api/runs/{run_id}/characters").json() if x["name"] == "Testheld")
    assert member.get(f"/api/runs/{run_id}/characters/{held['id']}").json()["armory_id"] == cid


def test_taeglich_faellig(make_client, fake, database_url):
    c = login(make_client, fake, MEMBER)
    fresh = c.post("/api/armory", json=NEW, headers=ORIGIN).json()["id"]
    old = c.post("/api/armory", json={**NEW, "character_id": "alt="}, headers=ORIGIN).json()["id"]
    stuck = c.post("/api/armory", json={**NEW, "character_id": "offen="}, headers=ORIGIN).json()["id"]
    age(database_url, old, hours=25)
    db_run(database_url, lambda db: db.execute(update(Character).where(Character.id == stuck).values(status="offen")))

    async def due():
        engine = create_async_engine(database_url)
        armory = Armory(async_sessionmaker(engine, expire_on_commit=False),
                        NC(httpx.AsyncClient(transport=httpx.MockTransport(fake.nc)), pause=0))
        ids = await armory.due()
        await engine.dispose()
        return ids
    assert sorted(asyncio.run(due())) == sorted([old, stuck]) and fresh not in asyncio.run(due())
