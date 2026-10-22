"""Momentaufnahmen der Mitspieler: angelegt beim Upload, gefüllt im Hintergrund. Nur erfundene Daten."""
import asyncio
import time

import httpx
from nexproto import NexLog, pack, unpack
from sqlalchemy import select
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from nexhub_api.characters import players_of
from nexhub_api.models import RunCharacter

from .conftest import MEMBER
from .fake_nc import search_row
from .test_devices import ORIGIN, pair
from .test_runs import nexlog, upload

ON = {"hub_aion2_enabled": True}


def with_servers(data: bytes, servers: dict[str, int]) -> bytes:
    """Actors bekommen eine serverId (wie A2Tools sie schreibt), Schlüssel = nickname."""
    log = unpack(data).model_dump(mode="json")
    for f in log["fights"]:
        for a in f["actors"]:
            a["serverId"] = servers.get(a["nickname"], 0)
    return pack(NexLog.model_validate(log))


def rows(database_url: str, run_id: int) -> dict[str, RunCharacter]:
    async def go() -> list[RunCharacter]:
        engine = create_async_engine(database_url)
        async with async_sessionmaker(engine)() as db:
            found = (await db.scalars(select(RunCharacter).where(RunCharacter.run_id == run_id))).all()
        await engine.dispose()
        return list(found)
    return {r.name: r for r in asyncio.run(go())}


def test_spieler_aus_den_kaempfen():
    log = unpack(with_servers(nexlog(), {"Testheld": 2302}))
    # Mo***n ist über names zu Moonlin aufgelöst, hat aber keine serverId
    assert sorted(players_of(log)) == [("Moonlin", "cleric", 0), ("Testheld", "ranger", 2302)]


def test_echte_server_id_gewinnt():
    data = unpack(nexlog()).model_dump(mode="json")
    data["fights"][0]["actors"][0]["serverId"] = 0
    data["fights"][1]["actors"][0]["serverId"] = 2302
    assert ("Testheld", "ranger", 2302) in players_of(NexLog.model_validate(data))


def test_upload_legt_an_und_fuellt(make_client, fake, as_user, database_url):
    with make_client(**ON) as c:
        token = pair(c, as_user(MEMBER))
        run_id = upload(c, token, with_servers(nexlog(), {"Testheld": 2302})).json()["id"]
    found = rows(database_url, run_id)
    held, moon = found["Testheld"], found["Moonlin"]
    assert held.status == "ok" and held.combat_power == 123456 and held.item_level == 2554
    assert held.nc_character_id == "abc=" and held.server_id == 2302 and held.fetched_at
    assert held.data["equipment"][0]["name"] == "Testbogen"
    assert moon.status == "nicht_gefunden" and moon.error == "Server unbekannt" and moon.data is None


def test_maskierter_name_fragt_nc_nicht(make_client, fake, as_user, database_url):
    data = unpack(with_servers(nexlog(), {"Testheld": 2302, "Mo***n": 2302})).model_dump(mode="json")
    data["names"] = {}
    with make_client(**ON) as c:
        token = pair(c, as_user(MEMBER))
        run_id = upload(c, token, pack(NexLog.model_validate(data))).json()["id"]
    assert rows(database_url, run_id)["Mo***n"].status == "name_maskiert"
    # nur Testheld wurde gesucht (eine Suche, ein Profil, eine Ausrüstung, ein Brett)
    assert fake.nc.calls.count("/aion2global/search/v2/character") == 1


def test_fehler_trifft_nur_den_spieler(make_client, fake, as_user, database_url):
    fake.nc.rows = [search_row("Testheld"), search_row("Moonlin", cid="moon")]
    fake.nc.fail_for = {"moon"}
    with make_client(**ON) as c:
        token = pair(c, as_user(MEMBER))
        run_id = upload(c, token, with_servers(nexlog(), {"Testheld": 2302, "Mo***n": 2302})).json()["id"]
    found = rows(database_url, run_id)
    assert found["Testheld"].status == "ok"
    assert found["Moonlin"].status == "fehler" and found["Moonlin"].error == "HTTP 500"


def test_duplikat_ruft_nichts_ab(make_client, fake, as_user, database_url):
    data = with_servers(nexlog(), {"Testheld": 2302})
    with make_client(**ON) as c:
        token = pair(c, as_user(MEMBER))
        run_id = upload(c, token, data).json()["id"]
        before = len(fake.nc.calls)
        assert upload(c, token, data).json()["duplicate"] is True
        assert len(fake.nc.calls) == before
    assert len(rows(database_url, run_id)) == 2


def test_ausgeschaltet_keine_zeilen(make_client, fake, as_user, database_url):
    with make_client() as c:
        run_id = upload(c, pair(c, as_user(MEMBER)), with_servers(nexlog(), {"Testheld": 2302})).json()["id"]
    assert rows(database_url, run_id) == {} and fake.nc.calls == []


def test_offene_zeilen_beim_start_nachholen(make_client, fake, as_user, database_url):
    fake.nc.routes["/aion2global/search/v2/character"] = httpx.ConnectError("weg")
    with make_client(**ON) as c:
        run_id = upload(c, pair(c, as_user(MEMBER)), with_servers(nexlog(), {"Testheld": 2302})).json()["id"]
    assert rows(database_url, run_id)["Testheld"].status == "fehler"

    async def reopen() -> None:
        engine = create_async_engine(database_url)
        async with async_sessionmaker(engine)() as db:
            row = await db.scalar(select(RunCharacter).where(RunCharacter.name == "Testheld"))
            row.status, row.error = "offen", None
            await db.commit()
        await engine.dispose()
    asyncio.run(reopen())

    fake.nc.routes = {}
    with make_client(**ON):
        # resume() läuft neben dem Webserver; warten, bis die Zeile gefüllt ist
        for _ in range(40):
            held = rows(database_url, run_id)["Testheld"]
            if held.status != "offen":
                break
            time.sleep(0.05)
    assert held.status == "ok"


def test_loeschen_entfernt_momentaufnahmen(make_client, fake, as_user, database_url):
    with make_client(**ON) as c:
        member = as_user(MEMBER)
        run_id = upload(c, pair(c, member), with_servers(nexlog(), {"Testheld": 2302})).json()["id"]
        assert member.delete(f"/api/runs/{run_id}", headers=ORIGIN).status_code == 204
    assert rows(database_url, run_id) == {}


def test_routen(make_client, fake, as_user):
    with make_client(**ON) as c:
        member = as_user(MEMBER)
        run_id = upload(c, pair(c, member), with_servers(nexlog(), {"Testheld": 2302})).json()["id"]
        listed = member.get(f"/api/runs/{run_id}/characters").json()
        assert [(x["name"], x["status"]) for x in listed] == [("Moonlin", "nicht_gefunden"), ("Testheld", "ok")]
        held = next(x for x in listed if x["name"] == "Testheld")
        assert held["combat_power"] == 123456 and held["item_level"] == 2554 and "data" not in held
        detail = member.get(f"/api/runs/{run_id}/characters/{held['id']}").json()
        assert detail["data"]["profile"]["name"] == "Testheld" and detail["error"] is None
        assert member.get(f"/api/runs/{run_id}/characters/999999").status_code == 404
        assert member.get("/api/runs/999999/characters").status_code == 404


def test_routen_nur_mit_login(client):
    assert client.get("/api/runs/1/characters").status_code == 401
    assert client.get("/api/runs/1/characters/1").status_code == 401


def test_geteilt_ohne_profile(make_client, fake, as_user):
    with make_client(**ON) as c:
        member = as_user(MEMBER)
        run_id = upload(c, pair(c, member), with_servers(nexlog(), {"Testheld": 2302})).json()["id"]
        token = member.post(f"/api/runs/{run_id}/share", headers=ORIGIN).json()["share_url"].rsplit("/", 1)[1]
        public = c.get(f"/api/public/runs/{token}")
        assert public.status_code == 200
        assert "Testbogen" not in public.text and "123456" not in public.text and "characters" not in public.text


def test_refresh(make_client, fake, as_user):
    from .conftest import ADMIN, log_in
    fake.nc.routes["/aion2global/search/v2/character"] = 503
    member = as_user(MEMBER)
    with make_client(**ON) as daemon, make_client(**ON) as admin:
        # Neuholen braucht eine App mit eingeschaltetem Abruf; as_user() baut eine ohne
        fake.user = ADMIN
        log_in(admin)
        run_id = upload(daemon, pair(daemon, admin), with_servers(nexlog(), {"Testheld": 2302})).json()["id"]
        assert member.post(f"/api/runs/{run_id}/characters/refresh", headers=ORIGIN).status_code == 403
        fake.nc.routes = {}
        r = admin.post(f"/api/runs/{run_id}/characters/refresh", headers=ORIGIN)
        # Testheld war fehler, Moonlin nicht_gefunden: beide neu
        assert r.status_code == 202 and r.json() == {"started": 2}
        statuses = {x["name"]: x["status"] for x in admin.get(f"/api/runs/{run_id}/characters").json()}
        assert statuses == {"Testheld": "ok", "Moonlin": "nicht_gefunden"}
        # zweites Mal innerhalb von 10 Minuten
        assert admin.post(f"/api/runs/{run_id}/characters/refresh", headers=ORIGIN).status_code == 429
