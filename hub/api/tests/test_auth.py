import base64
import hashlib
from urllib.parse import parse_qs, urlsplit

from nexhub_api.deps import SESSION_COOKIE
from nexhub_api.routes.auth import STATE_COOKIE, safe_next

from .conftest import ADMIN, MEMBER, STRANGER, BASE, log_in, start_login


def test_login_leitet_mit_pkce_zu_discord(client):
    r = client.get("/api/auth/login")
    url = urlsplit(r.headers["location"])
    q = parse_qs(url.query)
    assert url.netloc == "discord.com"
    assert q["redirect_uri"] == [f"{BASE}/api/auth/callback"]
    assert q["code_challenge_method"] == ["S256"]
    assert q["scope"] == ["identify guilds.members.read"]
    assert STATE_COOKIE in r.cookies
    assert "httponly" in r.headers["set-cookie"].lower()


def test_ohne_mitgliedsrolle_nur_identify(make_client):
    with make_client(hub_member_role_id="") as c:
        assert start_login(c)["scope"] == "identify"


def test_ohne_discord_daten_kein_login(make_client):
    with make_client(discord_client_secret="") as c:
        assert c.get("/api/auth/login").status_code == 503


def test_admin_meldet_sich_an(client, fake):
    r = log_in(client, next="/hub/runs")
    assert r.status_code == 302 and r.headers["location"] == "/hub/runs"
    assert SESSION_COOKIE in client.cookies
    me = client.get("/api/me").json()
    assert me == {"discord_id": str(ADMIN), "name": "Testname",
                  "avatar_url": f"https://cdn.discordapp.com/avatars/{ADMIN}/abc123.png?size=128",
                  "role": "admin"}
    # Admins brauchen keine Rollenabfrage; der Discord-Token wird zurückgegeben
    assert "POST /oauth2/token/revoke" in fake.calls
    assert not any("/guilds/" in c for c in fake.calls)


def test_pkce_verifier_passt_zur_challenge(client, fake):
    q = start_login(client)
    from itsdangerous import URLSafeTimedSerializer
    saved = URLSafeTimedSerializer("test-geheimnis", salt="nexhub-oauth").loads(client.cookies[STATE_COOKIE])
    expected = base64.urlsafe_b64encode(hashlib.sha256(saved["v"].encode()).digest()).rstrip(b"=").decode()
    assert q["code_challenge"] == expected


def test_mitglied_ueber_rolle(client, fake):
    fake.user = MEMBER
    log_in(client)
    assert client.get("/api/me").json()["role"] == "member"


def test_fremde_kommen_nicht_rein(client, fake):
    fake.user = STRANGER
    r = log_in(client)
    assert r.headers["location"] == f"/login?fehler=nicht_freigeschaltet&id={STRANGER}"
    assert SESSION_COOKIE not in client.cookies
    assert client.get("/api/me").status_code == 401


def test_nicht_auf_dem_server(client, fake):
    fake.user = 444
    assert "nicht_freigeschaltet" in log_in(client).headers["location"]


def test_falscher_state(client):
    start_login(client)
    r = client.get("/api/auth/callback", params={"code": "x", "state": "falsch"})
    assert r.headers["location"] == "/login?fehler=ungueltig"


def test_ohne_state_cookie(client):
    r = client.get("/api/auth/callback", params={"code": "x", "state": "y"})
    assert r.headers["location"] == "/login?fehler=abgelaufen"


def test_abgebrochen(client):
    q = start_login(client)
    r = client.get("/api/auth/callback", params={"error": "access_denied", "state": q["state"]})
    assert r.headers["location"] == "/login?fehler=abgebrochen"


def test_discord_fehler(client, fake):
    fake.token_status = 400
    assert log_in(client).headers["location"] == "/login?fehler=discord"


def test_kein_offener_redirect():
    assert safe_next("//boese.example") == "/hub"
    assert safe_next("/\\boese.example") == "/hub"
    assert safe_next("https://boese.example") == "/hub"
    assert safe_next("/reports?x=1") == "/reports?x=1"


def test_ohne_next_geht_es_in_den_hub(client):
    q = start_login(client)
    r = client.get("/api/auth/callback", params={"code": "c", "state": q["state"]})
    assert r.headers["location"] == "/hub"


def test_logout_braucht_eigene_herkunft(client):
    log_in(client)
    assert client.post("/api/auth/logout").status_code == 403
    assert client.post("/api/auth/logout", headers={"origin": "https://boese.example"}).status_code == 403
    assert client.get("/api/me").status_code == 200
    assert client.post("/api/auth/logout", headers={"origin": BASE}).status_code == 204
    assert client.get("/api/me").status_code == 401


def test_logout_beendet_die_sitzung_in_der_datenbank(client):
    log_in(client)
    token = client.cookies[SESSION_COOKIE]
    client.post("/api/auth/logout", headers={"origin": BASE})
    client.cookies.set(SESSION_COOKIE, token)
    assert client.get("/api/me").status_code == 401


def test_abgelaufene_sitzung(make_client):
    with make_client(hub_session_days=-1) as c:
        r = log_in(c)
        # Der Browser hätte den Cookie schon verworfen; hier zählt, dass der Server ablehnt
        token = r.headers["set-cookie"].split(f"{SESSION_COOKIE}=")[1].split(";")[0]
        c.cookies.set(SESSION_COOKIE, token)
        assert c.get("/api/me").status_code == 401


def test_zweiter_login_aktualisiert_das_konto(client, fake):
    log_in(client)
    fake.roles[ADMIN] = []
    log_in(client)
    assert client.get("/api/me").json()["role"] == "admin"
