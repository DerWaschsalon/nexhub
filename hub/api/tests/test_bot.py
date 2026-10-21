import json

import httpx

from .conftest import ADMIN, BASE, MEMBER, log_in

ORIGIN = {"origin": BASE}
BOT = {"bot_control_url": "http://bot:8790/", "bot_control_key": "s" * 32}


def test_nur_admins(make_client, as_user, fake):
    fake.bot = lambda r: httpx.Response(200, json={"ready": True})
    with make_client(**BOT) as anon:
        assert anon.get("/api/admin/bot/status").status_code == 401
    assert as_user(MEMBER).get("/api/admin/bot/status").status_code == 403


def test_ohne_einstellung_nicht_verbunden(as_user):
    r = as_user(ADMIN).get("/api/admin/bot/status")
    assert r.status_code == 503 and "nicht mit dem Hub verbunden" in r.json()["detail"]


def test_reicht_anfrage_mit_schluessel_durch(make_client, fake):
    seen: list[httpx.Request] = []

    def bot(request: httpx.Request) -> httpx.Response:
        seen.append(request)
        if request.method == "DELETE":
            return httpx.Response(204)
        return httpx.Response(400, json={"detail": "Kanal gibt es nicht"})

    fake.bot = bot
    with make_client(**BOT) as admin:
        log_in(admin)
        r = admin.put("/api/admin/bot/sections/allgemein", json={"values": {"log_channel": "1"}}, headers=ORIGIN)
        assert r.status_code == 400 and r.json()["detail"] == "Kanal gibt es nicht"
        assert admin.delete("/api/admin/bot/commands/regeln", headers=ORIGIN).status_code == 204

    put = seen[0]
    assert str(put.url) == "http://bot:8790/control/sections/allgemein"
    assert put.headers["authorization"] == "Bearer " + "s" * 32
    assert put.headers["x-hub-user"] == "Testname" and put.headers["x-hub-user-id"] == str(ADMIN)
    assert json.loads(put.content) == {"values": {"log_channel": "1"}}
    assert seen[1].method == "DELETE" and seen[1].url.path == "/control/commands/regeln"


def test_fremde_herkunft_und_pfade(make_client, fake):
    calls = []
    fake.bot = lambda r: calls.append(r) or httpx.Response(200, json={})
    with make_client(**BOT) as admin:
        log_in(admin)
        # Ändernde Anfragen nur von der eigenen Seite (CSRF), wie im restlichen Hub
        assert admin.put("/api/admin/bot/matrix", json={}).status_code == 403
        assert admin.get("/api/admin/bot/a.b").status_code == 404
        assert admin.get("/api/admin/bot/").status_code == 404
    assert calls == []


def test_fehler_des_bots(make_client, fake):
    with make_client(**BOT) as admin:
        log_in(admin)

        fake.bot = lambda r: httpx.Response(401, json={"detail": "Schlüssel fehlt oder falsch"})
        r = admin.get("/api/admin/bot/status")
        assert r.status_code == 502 and "Schlüssel" in r.json()["detail"]  # kein 401: Admin bleibt angemeldet

        def down(request):
            raise httpx.ConnectError("refused", request=request)
        fake.bot = down
        assert admin.get("/api/admin/bot/status").status_code == 502

        def slow(request):
            raise httpx.ReadTimeout("timeout", request=request)
        fake.bot = slow
        assert admin.get("/api/admin/bot/status").status_code == 504

        fake.bot = lambda r: httpx.Response(500, text="<html>")
        assert admin.get("/api/admin/bot/status").status_code == 502
