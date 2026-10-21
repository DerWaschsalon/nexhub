import logging

from nexhub_api.logs import HideSecretQuery

from .conftest import BASE, log_in


def test_health(client):
    assert client.get("/api/health").json() == {"ok": True}


def test_oeffentliche_info_ohne_login(client, make_client):
    assert client.get("/api/public/info").json() == {"login": True, "operator": None, "hoster": None}
    with make_client(discord_client_id="") as c:
        assert c.get("/api/public/info").json()["login"] is False


def test_impressum_aus_der_konfiguration(make_client):
    with make_client(hub_operator_name=" Erika Muster ", hub_operator_address="Musterweg 1; 12345 Musterstadt;",
                     hub_operator_email="", hub_hoster="Beispiel-Hosting, Deutschland") as c:
        info = c.get("/api/public/info").json()
    assert info["operator"] == {"name": "Erika Muster", "address": ["Musterweg 1", "12345 Musterstadt"], "email": None}
    assert info["hoster"] == "Beispiel-Hosting, Deutschland"


def test_ohne_web_dir_nur_api(client):
    assert client.get("/irgendwas").status_code == 404


def test_web_oberflaeche_mit_fallback(make_client, tmp_path):
    web = tmp_path / "web"
    (web / "_app" / "immutable").mkdir(parents=True)
    (web / "200.html").write_text("<html>hub</html>")
    (web / "_app" / "immutable" / "a.js").write_text("js")
    (tmp_path / "geheim.txt").write_text("nein")
    with make_client(hub_web_dir=str(web)) as c:
        assert c.get("/").text == "<html>hub</html>"
        assert c.get("/hub/admin").text == "<html>hub</html>"
        r = c.get("/_app/immutable/a.js")
        assert r.text == "js" and "immutable" in r.headers["cache-control"]
        assert c.get("/../geheim.txt").text == "<html>hub</html>"
        assert c.get("/%2e%2e/geheim.txt").text == "<html>hub</html>"
        assert c.get("/api/gibtsnicht").status_code == 404


def test_herkunftspruefung_nur_mit_cookie(client):
    # Ohne Sitzungscookie greift die Prüfung nicht (später: Geräte mit eigenem Token)
    assert client.post("/api/auth/logout").status_code == 204
    log_in(client)
    assert client.post("/api/admin/users/1/logout").status_code == 403
    assert client.post("/api/admin/users/1/logout", headers={"origin": BASE}).status_code == 204


def _access_line(path: str) -> str:
    record = logging.LogRecord("uvicorn.access", logging.INFO, "", 0, '%s - "%s %s HTTP/%s" %d',
                               ("1.2.3.4:5", "GET", path, "1.1", 302), None)
    HideSecretQuery().filter(record)
    return record.getMessage()


def test_zugriffslog_ohne_oauth_code():
    line = _access_line("/api/auth/callback?code=GEHEIM&state=AUCHGEHEIM")
    assert "GEHEIM" not in line and "/api/auth/callback?…" in line
    assert "next=%2Fhub" in _access_line("/api/auth/login?next=%2Fhub")
