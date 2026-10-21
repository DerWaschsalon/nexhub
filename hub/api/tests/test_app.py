from .conftest import BASE


def test_health(client):
    assert client.get("/api/health").json() == {"ok": True, "login": True}


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
        assert c.get("/reports/42").text == "<html>hub</html>"
        r = c.get("/_app/immutable/a.js")
        assert r.text == "js" and "immutable" in r.headers["cache-control"]
        assert c.get("/../geheim.txt").text == "<html>hub</html>"
        assert c.get("/%2e%2e/geheim.txt").text == "<html>hub</html>"
        assert c.get("/api/gibtsnicht").status_code == 404
