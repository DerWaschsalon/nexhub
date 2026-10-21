from datetime import UTC, datetime, timedelta

from nexhub_api.routes.devices import ALPHABET, MAX_OPEN_PAIRINGS, normalize_code

from .conftest import ADMIN, BASE, MEMBER

ORIGIN = {"origin": BASE}


def start(client, name="Fabio-PC"):
    r = client.post("/api/devices/pair", json={"name": name, "version": "0.6.0"})
    assert r.status_code == 200, r.text
    return r.json()


def bearer(token):
    return {"authorization": f"Bearer {token}"}


def pair(daemon, user, name=None) -> str:
    """Ganze Kopplung: Daemon startet, Mensch bestätigt, Daemon holt sein Token."""
    p = start(daemon)
    r = user.post("/api/devices/pair/approve", json={"code": p["user_code"], "name": name}, headers=ORIGIN)
    assert r.status_code == 200, r.text
    r = daemon.post("/api/devices/pair/poll", json={"device_code": p["device_code"]})
    assert r.json()["status"] == "approved"
    return r.json()["token"]


def test_kopplung_von_anfang_bis_ende(client, as_user):
    p = start(client)
    assert len(p["user_code"]) == 9 and p["user_code"][4] == "-"
    assert all(c in ALPHABET for c in p["user_code"].replace("-", ""))
    assert p["verification_uri_complete"] == f"{BASE}/hub/geraete?code={p['user_code']}"
    assert p["interval"] == 5 and p["expires_in"] == 600

    poll = lambda: client.post("/api/devices/pair/poll", json={"device_code": p["device_code"]})  # noqa: E731
    assert poll().json() == {"status": "pending", "token": None, "device_id": None, "device_name": None}

    admin = as_user(ADMIN)
    # Kleinbuchstaben und Leerzeichen beim Abtippen sind egal
    code = p["user_code"].lower().replace("-", " ")
    r = admin.post("/api/devices/pair/approve", json={"code": code, "name": "Gaming-PC"}, headers=ORIGIN)
    assert r.json() == {"name": "Gaming-PC"}

    r = poll().json()
    assert r["status"] == "approved" and r["device_name"] == "Gaming-PC" and len(r["token"]) > 30
    # Das Token gibt es genau einmal
    assert poll().status_code == 410

    me = client.get("/api/devices/me", headers={**bearer(r["token"]), "x-nexboard-version": "0.6.0"})
    assert me.json() == {"id": r["device_id"], "name": "Gaming-PC", "owner": "Testname"}
    devices = admin.get("/api/devices").json()
    assert [(d["name"], d["version"]) for d in devices] == [("Gaming-PC", "0.6.0")]
    assert devices[0]["last_seen_at"] is not None


def test_ohne_namen_gilt_der_vorschlag_des_daemons(client, as_user):
    token = pair(client, as_user(MEMBER))
    assert client.get("/api/devices/me", headers=bearer(token)).json()["name"] == "Fabio-PC"


def test_bestaetigen_braucht_login_und_gueltigen_code(client, as_user):
    p = start(client)
    assert client.post("/api/devices/pair/approve", json={"code": p["user_code"]}).status_code == 401
    member = as_user(MEMBER)
    assert member.post("/api/devices/pair/approve", json={"code": "BBBB-BBBB"}, headers=ORIGIN).status_code == 404
    assert member.post("/api/devices/pair/approve", json={"code": p["user_code"]}, headers=ORIGIN).status_code == 200
    # Zweimal bestätigen geht nicht
    assert member.post("/api/devices/pair/approve", json={"code": p["user_code"]}, headers=ORIGIN).status_code == 404


def test_abgelaufene_kopplung(client, as_user, monkeypatch):
    import nexhub_api.routes.devices as devices
    monkeypatch.setattr(devices, "PAIRING_TTL_S", -1)
    p = start(client)
    member = as_user(MEMBER)
    assert member.post("/api/devices/pair/approve", json={"code": p["user_code"]}, headers=ORIGIN).status_code == 404
    assert client.post("/api/devices/pair/poll", json={"device_code": p["device_code"]}).status_code == 410


def test_unbekannter_device_code(client):
    assert client.post("/api/devices/pair/poll", json={"device_code": "gibtsnicht"}).status_code == 410


def test_zu_viele_offene_kopplungen(client):
    for _ in range(MAX_OPEN_PAIRINGS):
        start(client)
    assert client.post("/api/devices/pair", json={}).status_code == 429


def test_geraete_token(client, as_user):
    token = pair(client, as_user(MEMBER))
    assert client.get("/api/devices/me").status_code == 401
    assert client.get("/api/devices/me", headers=bearer("falsch")).status_code == 401
    assert client.get("/api/devices/me", headers={"authorization": f"Basic {token}"}).status_code == 401
    assert client.get("/api/devices/me", headers=bearer(token)).status_code == 200


def test_geraet_koppelt_sich_selbst_ab(client, as_user):
    member = as_user(MEMBER)
    token = pair(client, member)
    assert client.delete("/api/devices/me", headers=bearer(token)).status_code == 204
    assert client.get("/api/devices/me", headers=bearer(token)).status_code == 401
    assert member.get("/api/devices").json() == []


def test_geraet_entfernen_nur_eigenes_oder_als_admin(client, as_user):
    member, admin = as_user(MEMBER), as_user(ADMIN)
    token = pair(client, member)
    other = pair(client, admin, name="Admin-PC")
    mine = member.get("/api/devices").json()[0]["id"]
    theirs = admin.get("/api/devices").json()[0]["id"]

    assert member.delete(f"/api/devices/{theirs}", headers=ORIGIN).status_code == 404
    assert member.delete(f"/api/devices/{mine}").status_code == 403  # ohne Origin (CSRF-Schutz)
    assert admin.delete(f"/api/devices/{mine}", headers=ORIGIN).status_code == 204
    assert client.get("/api/devices/me", headers=bearer(token)).status_code == 401
    assert client.get("/api/devices/me", headers=bearer(other)).status_code == 200


def test_gesperrtes_konto_sperrt_seine_geraete(client, as_user):
    member, admin = as_user(MEMBER), as_user(ADMIN)
    token = pair(client, member)
    target = next(a for a in admin.get("/api/admin/users").json() if a["discord_id"] == str(MEMBER))["id"]
    admin.post(f"/api/admin/users/{target}/block", headers=ORIGIN)
    assert client.get("/api/devices/me", headers=bearer(token)).status_code == 401


def test_code_normalisieren():
    assert normalize_code(" bcdf-ghjk ") == "BCDFGHJK"
    assert normalize_code("A0O1-bcdf") == "BCDF"  # nicht vorkommende Zeichen fallen raus
