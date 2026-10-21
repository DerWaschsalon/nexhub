"""NexHub-Anbindung gegen einen nachgebauten Hub (gleiche Endpunkte wie hub/api, routes/devices.py)."""
import asyncio

import pytest
from aiohttp import web
from pydantic import ValidationError

from deckbar_daemon import hub as hubmod
from deckbar_daemon.hub import Hub, HubError


async def fake_hub(polls_until_approved: int = 1):
    """Hub, der nach `polls_until_approved` Nachfragen bestätigt; merkt sich, was ankam."""
    seen = {"pair": [], "polls": 0, "auth": [], "deleted": False, "valid": True}

    async def pair(request):
        seen["pair"].append(await request.json())
        return web.json_response({"device_code": "dc", "user_code": "BCDF-GHJK",
                                  "verification_uri": "http://x/hub/geraete",
                                  "verification_uri_complete": "http://x/hub/geraete?code=BCDF-GHJK",
                                  "expires_in": 600, "interval": 0})

    async def poll(request):
        body = await request.json()
        if body["device_code"] != "dc":
            return web.json_response({"detail": "Kopplung abgelaufen"}, status=410)
        seen["polls"] += 1
        if seen["polls"] < polls_until_approved:
            return web.json_response({"status": "pending"})
        return web.json_response({"status": "approved", "token": "geraete-token", "device_id": 1, "device_name": "PC"})

    async def me(request):
        seen["auth"].append((request.headers.get("Authorization"), request.headers.get("X-NexBoard-Version")))
        if not seen["valid"] or request.headers.get("Authorization") != "Bearer geraete-token":
            return web.json_response({"detail": "Gerät unbekannt"}, status=401)
        if request.method == "DELETE":
            seen["deleted"] = True
            return web.Response(status=204)
        return web.json_response({"id": 1, "name": "PC", "owner": "Testheld"})

    app = web.Application()
    app.router.add_post("/api/devices/pair", pair)
    app.router.add_post("/api/devices/pair/poll", poll)
    app.router.add_route("*", "/api/devices/me", me)
    runner = web.AppRunner(app)
    await runner.setup()
    site = web.TCPSite(runner, "127.0.0.1", 0)
    await site.start()
    return runner, f"http://127.0.0.1:{site._server.sockets[0].getsockname()[1]}", seen


async def wait_for(cond, timeout=3.0):
    for _ in range(int(timeout / 0.01)):
        if cond():
            return
        await asyncio.sleep(0.01)
    raise AssertionError("Bedingung nicht erreicht")


@pytest.fixture(autouse=True)
def fast_poll(monkeypatch):
    monkeypatch.setattr(hubmod, "MIN_POLL_S", 0.0)


async def test_koppeln_von_anfang_bis_ende(tmp_path):
    runner, url, seen = await fake_hub(polls_until_approved=3)
    hub = Hub(tmp_path)
    try:
        hub.update({"url": url + "/", "name": "Gaming-PC"})
        assert hub.settings.url == url  # Schrägstrich am Ende weg
        await hub.start_pairing()
        assert hub.status == "pairing" and hub.pairing["user_code"] == "BCDF-GHJK"
        assert seen["pair"][0]["name"] == "Gaming-PC"
        await wait_for(lambda: hub.status == "paired")
        assert seen["polls"] == 3 and hub.pairing is None
        assert hub.account == {"device": "PC", "owner": "Testheld"}
        assert seen["auth"][-1][1]  # Version geht mit
        # Token steht in hub.yaml (nur für den Besitzer lesbar), nie in info()
        assert (tmp_path / "hub.yaml").stat().st_mode & 0o777 == 0o600
        assert "geraete-token" in (tmp_path / "hub.yaml").read_text()
        assert "geraete-token" not in str(hub.info())
        # Neustart: Token bleibt
        assert Hub(tmp_path).settings.token == "geraete-token"
    finally:
        await hub.close()
        await runner.cleanup()


async def test_abkoppeln_meldet_ab_und_vergisst_das_token(tmp_path):
    runner, url, seen = await fake_hub()
    hub = Hub(tmp_path)
    try:
        hub.update({"url": url})
        await hub.start_pairing()
        await wait_for(lambda: hub.status == "paired")
        await hub.unpair()
        assert seen["deleted"] and hub.status == "unpaired" and hub.settings.token == ""
        assert Hub(tmp_path).settings.token == ""
    finally:
        await hub.close()
        await runner.cleanup()


async def test_im_hub_entfernt(tmp_path):
    runner, url, seen = await fake_hub()
    hub = Hub(tmp_path)
    try:
        hub.update({"url": url})
        await hub.start_pairing()
        await wait_for(lambda: hub.status == "paired")
        seen["valid"] = False
        await hub.check()
        assert hub.status == "unpaired" and "entfernt" in hub.detail and hub.settings.token == ""
    finally:
        await hub.close()
        await runner.cleanup()


async def test_hub_nicht_erreichbar(tmp_path):
    hub = Hub(tmp_path)
    hub.save(hub.settings.model_copy(update={"url": "http://127.0.0.1:9", "token": "t"}))
    try:
        await hub.check()
        assert hub.status == "offline" and hub.settings.token == "t"  # Token bleibt, Hub ist nur weg
        with pytest.raises(HubError, match="nicht erreichbar"):
            await hub.start_pairing()
    finally:
        await hub.close()


async def test_neue_adresse_heisst_neu_koppeln(tmp_path):
    hub = Hub(tmp_path)
    hub.save(hub.settings.model_copy(update={"url": "https://a.example.com", "token": "t"}))
    hub.update({"name": "Anderer Name"})
    assert hub.settings.token == "t"
    hub.update({"url": "https://b.example.com"})
    assert hub.settings.token == "" and hub.status == "unpaired"


@pytest.mark.parametrize("url", ["http://hub.example.com", "ftp://x", "https://hub.example.com/pfad", "kein-url"])
def test_unsichere_oder_falsche_adressen(tmp_path, url):
    with pytest.raises(ValidationError):
        Hub(tmp_path).update({"url": url})


@pytest.mark.parametrize("url", ["https://hub.example.com", "http://localhost:8080", "http://127.0.0.1:8080", ""])
def test_erlaubte_adressen(tmp_path, url):
    assert Hub(tmp_path).update({"url": url}).url == url


async def test_abgelaufener_code(tmp_path):
    runner, url, _ = await fake_hub(polls_until_approved=10**6)
    hub = Hub(tmp_path)
    try:
        hub.update({"url": url})
        await hub.start_pairing()
        # Code abgelaufen: der Hub antwortet auf das nächste Nachfragen mit 410
        hub._poll_task.cancel()
        hub._poll_task = asyncio.create_task(hub._poll("anderer-code", 0, 600))
        await wait_for(lambda: hub.status == "unpaired")
        assert hub.pairing is None and "abgelaufen" in hub.detail
    finally:
        await hub.close()
        await runner.cleanup()
