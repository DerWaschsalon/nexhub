"""WebHost (bot/core/web.py): Routen der Module, Schutz der Steuer-API, ausgeschaltete Module."""

from __future__ import annotations

import asyncio
from typing import Any, ClassVar
from unittest.mock import MagicMock

import pytest
from aiohttp import web
from aiohttp.test_utils import TestClient, TestServer
from nexcore import EventBus, ModuleInfo, Paths

from bot.core import BotContext, BotModule
from bot.core.host import module_routes
from bot.core.web import RouteTable, control_app, control_key, public_app
from bot.hubpages import ApiError

KEY = "k" * 32


class Echo(BotModule):
    info: ClassVar[ModuleInfo] = ModuleInfo(
        id="test.echo", name="Echo", category="Test", icon="mdi-test", summary="Testmodul")

    def routes(self, r: RouteTable) -> None:
        r.control("GET", "/control/echo", self.echo)
        r.control("GET", "/control/kaputt", self.broken)
        r.open("GET", "/echo", self.public_echo)

    async def echo(self, _request: web.Request) -> dict[str, Any]:
        return {"ok": True}

    async def broken(self, _request: web.Request) -> None:
        raise ApiError(418, "Teekanne")

    async def public_echo(self, _request: web.Request) -> web.Response:
        return web.Response(text="hallo")


def module() -> Echo:
    return Echo(BotContext(bus=EventBus(), paths=Paths("test"), db=MagicMock(), client=MagicMock()))


def test_control_path_must_be_under_control() -> None:
    async def handler(_request: web.Request) -> None:
        return None

    with pytest.raises(ValueError):
        RouteTable().control("GET", "/anderswo", handler)


def test_module_routes_need_key_and_answer_503_when_off() -> None:
    async def go() -> None:
        echo = module()
        table = RouteTable()
        module_routes(echo, table)
        async with TestClient(TestServer(control_app(table, KEY))) as control, \
                TestClient(TestServer(public_app(table))) as public:
            auth = {"Authorization": f"Bearer {KEY}"}
            assert (await control.get("/control/echo")).status == 401
            off = await control.get("/control/echo", headers=auth)
            assert off.status == 503 and "Echo" in (await off.json())["detail"]
            assert (await public.get("/echo")).status == 503

            echo.active = True
            assert await (await control.get("/control/echo", headers=auth)).json() == {"ok": True}
            broken = await control.get("/control/kaputt", headers=auth)
            assert broken.status == 418 and (await broken.json())["detail"] == "Teekanne"
            assert await (await public.get("/echo")).text() == "hallo"
            # Die Steuer-API ist von außen nicht erreichbar
            assert (await public.get("/control/echo", headers=auth)).status == 404

    asyncio.run(go())


def test_control_key_too_short_keeps_api_off(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("BOT_CONTROL_KEY", "kurz")
    assert control_key() == ""
    monkeypatch.setenv("BOT_CONTROL_KEY", KEY)
    assert control_key() == KEY
    monkeypatch.delenv("BOT_CONTROL_KEY")
    assert control_key() == ""
