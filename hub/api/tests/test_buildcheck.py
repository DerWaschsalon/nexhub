"""Build-Check: Lauf, Sperren, Fehler, Teilen. NC und Abyss Logs nachgebaut (fake_nc.py, fake_abyss.py)."""
import json
from datetime import UTC, datetime, timedelta

from sqlalchemy import update

from nexhub_api.models import BuildCheck

from .conftest import BASE, MEMBER
from .fake_nc import search_row
from .test_armory import NEW, ON, db_run, login
from .test_devices import ORIGIN


def add(c, fake, character_id: str = "abc=", fail: bool = False) -> int:
    """Charakter eintragen; mit `fail` antwortet sein Profil mit 500 (keine Momentaufnahme)."""
    if fail:
        fake.nc.fail_for.add(character_id)
    return c.post("/api/armory", json={**NEW, "character_id": character_id}, headers=ORIGIN).json()["id"]


def top_rows(fake, n: int = 20) -> None:
    """Suchtreffer für die Namen aus der Rangliste (Bogenheld, Bogenheld2 …), je eine eigene ID."""
    fake.nc.rows += [search_row("Bogenheld", cid="top1%3D")]
    fake.nc.rows += [search_row(f"Bogenheld{i}", cid=f"top{i}%3D") for i in range(2, n + 1)]


def start(c, cid: int):
    return c.post(f"/api/armory/{cid}/check", headers=ORIGIN)


def set_check(database_url, cid: int, **values) -> None:
    db_run(database_url, lambda db: db.execute(update(BuildCheck).where(BuildCheck.character_id == cid).values(**values)))


def ago(minutes: int) -> datetime:
    return datetime.now(UTC) - timedelta(minutes=minutes)


def test_check_laeuft_und_zeigt_ergebnis(make_client, fake):
    top_rows(fake)
    c = login(make_client, fake, MEMBER)
    cid = add(c, fake)
    assert start(c, cid).status_code == 202
    d = c.get(f"/api/armory/{cid}/check").json()  # TestClient: der Hintergrundlauf ist schon fertig
    assert d["status"] == "fertig" and d["size"] == 15 and d["progress"] == 15
    assert len(d["result"]["fields"]) > 5 and "todo" in d["result"]
    assert "Bogenheld" not in json.dumps(d)  # keine Namen der Top-Spieler
    assert "class=Ranger" in fake.abyss.last_query


def test_sperre_und_ohne_daten(make_client, fake):
    top_rows(fake)
    c = login(make_client, fake, MEMBER)
    cid = add(c, fake)
    start(c, cid)
    assert start(c, cid).status_code == 429
    no_data = add(c, fake, character_id="kaputt=", fail=True)
    r = start(c, no_data)
    assert r.status_code == 422 and r.json()["detail"]
    assert c.get(f"/api/armory/{no_data}/check").status_code == 404


def test_fehler_behalten_altes_ergebnis(make_client, fake, database_url):
    top_rows(fake)
    c = login(make_client, fake, MEMBER)
    cid = add(c, fake)
    start(c, cid)
    set_check(database_url, cid, started_at=ago(11))
    fake.abyss.routes["/v1/leaderboards"] = 500
    assert start(c, cid).status_code == 202
    d = c.get(f"/api/armory/{cid}/check").json()
    assert d["status"] == "fehler" and "Abyss Logs" in d["error"] and d["result"]["fields"]

    fake.abyss.routes.pop("/v1/leaderboards")
    fake.abyss.size = 3
    set_check(database_url, cid, started_at=ago(11))
    start(c, cid)
    d = c.get(f"/api/armory/{cid}/check").json()
    assert d["status"] == "fehler" and "Zu wenige" in d["error"]


def test_wenige_aber_genug(make_client, fake):
    top_rows(fake, n=6)
    fake.abyss.size = 6
    c = login(make_client, fake, MEMBER)
    cid = add(c, fake)
    start(c, cid)
    d = c.get(f"/api/armory/{cid}/check").json()
    assert (d["status"], d["size"]) == ("fertig", 6)


def test_haengender_lauf_darf_neu(make_client, fake, database_url):
    top_rows(fake)
    c = login(make_client, fake, MEMBER)
    cid = add(c, fake)
    start(c, cid)
    set_check(database_url, cid, status="läuft", started_at=ago(5))
    assert start(c, cid).status_code == 409
    set_check(database_url, cid, status="läuft", started_at=ago(20))
    assert start(c, cid).status_code == 202


def test_name_mehrdeutig_naechste_kampfkraft(make_client, fake):
    # zwei „Bogenheld“ (Rangliste: 123_000) auf zwei Servern; 2312 hat nur 90_000 → genommen wird 2302
    fake.nc.rows += [search_row("Bogenheld", server=2302, cid="a%3D"), search_row("Bogenheld", server=2312, cid="b%3D")]
    fake.nc.rows += [search_row(f"Bogenheld{i}", cid=f"top{i}%3D") for i in range(2, 21)]
    fake.nc.cp_for = {"b=": 90_000}
    c = login(make_client, fake, MEMBER)
    cid = add(c, fake)
    start(c, cid)
    assert "a=" in fake.nc.item_ids and "b=" not in fake.nc.item_ids


def test_teilen_oeffentlich(make_client, fake):
    top_rows(fake)
    c = login(make_client, fake, MEMBER)
    cid = add(c, fake)
    start(c, cid)
    url = c.post(f"/api/armory/{cid}/check/share", headers=ORIGIN).json()["share_url"]
    assert url.startswith(f"{BASE}/c/")
    token = url.rsplit("/", 1)[1]
    anyone = make_client(**ON)  # ohne Login
    anyone.__enter__()
    r = anyone.get(f"/api/public/check/{token}")
    assert r.status_code == 200 and "noindex" in r.headers["x-robots-tag"]
    body = r.json()
    assert body["name"] == "Testheld" and "owner" not in body and body["result"]["size"] == 15
    assert c.delete(f"/api/armory/{cid}/check/share", headers=ORIGIN).json() == {"share_url": None}
    assert anyone.get(f"/api/public/check/{token}").status_code == 404


def test_nur_mit_login(client):
    assert client.post("/api/armory/1/check").status_code == 401
    assert client.get("/api/public/check/gibtsnicht").status_code == 404
