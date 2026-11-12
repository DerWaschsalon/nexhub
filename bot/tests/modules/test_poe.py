"""Path of Exile: Embeds für Alarm, Tagespost und Preis, Steuer-Routen und die Abfrage beim Hub."""

from __future__ import annotations

import asyncio
import tempfile
from pathlib import Path
from types import SimpleNamespace
from typing import Any
from unittest.mock import AsyncMock, MagicMock

import discord
import pytest
from aiohttp import web
from aiohttp.test_utils import TestClient, TestServer
from nexcore import EventBus, Paths

from bot.core import BotContext
from bot.core.host import module_routes
from bot.core.hub import HubClient
from bot.core.web import RouteTable, control_app
from bot.db import Database
from bot.errors import UserError
from bot.hubpages import ApiError
from bot.modules.poe.prices import PoePrices
from bot.modules.poe.prices.embeds import alert_embed, daily_embed, price_embed

KEY = "k" * 32
AUTH = {"Authorization": f"Bearer {KEY}"}
GUILD = 5


def move(name: str, old: float, new: float, change: float) -> dict[str, Any]:
    return {"key": name.lower(), "name": name, "icon": None, "old": old, "new": new, "unit": "divine",
            "change": change, "url": f"https://poe.ninja/x/{name.lower()}"}


def alert(guild_id: Any = GUILD) -> dict[str, Any]:
    return {"guild_id": guild_id, "discord_id": 42, "game": "poe1", "league": "Mercenaries",
            **move("Mageblood", 100, 125, 25.0)}


def module(db: Database, channel: Any = None) -> PoePrices:
    client = SimpleNamespace(get_guild=lambda gid: object() if gid == GUILD else None,
                             get_channel=lambda cid: channel)
    prices = PoePrices(BotContext(bus=EventBus(), paths=Paths("test"), db=db, client=client))  # type: ignore[arg-type]
    prices.active = True
    return prices


def text_of(embed: discord.Embed) -> str:
    fields = " ".join(f"{f.name} {f.value}" for f in embed.fields)
    return f"{embed.title} {embed.description} {fields}"


def test_alert_embed() -> None:
    embed = alert_embed(alert())
    assert embed.title is not None and "Mageblood" in embed.title
    assert "+25 %" in text_of(embed)
    assert embed.url == "https://poe.ninja/x/mageblood"
    assert embed.footer.text == "Preise: poe.ninja"


def test_daily_embed_empty_side() -> None:
    embed = daily_embed({"guild_id": GUILD, "game": "poe2", "league": "Dawn", "up": [move("Exalted", 1, 2, 100.0)],
                         "down": []})
    losers = next(f for f in embed.fields if f.name == "Verlierer")
    assert losers.value == "keine"
    assert "Exalted" in text_of(embed)


def test_price_embed() -> None:
    embed = price_embed({"name": "Divine Orb", "price": 180.0, "unit": "chaos", "change_24h": -3.6,
                         "change_7d": None, "league": "Mercenaries", "url": "https://poe.ninja/x/divine",
                         "icon": None}, "poe1")
    assert embed.title == "Divine Orb" and embed.url == "https://poe.ninja/x/divine"
    assert "180 chaos" in text_of(embed) and "-4 %" in text_of(embed)


def with_db(test: Any) -> None:
    async def go() -> None:
        with tempfile.TemporaryDirectory() as d:
            db = Database(Path(d) / "t.sqlite3")
            await db.connect()
            try:
                await test(db)
            finally:
                await db.close()

    asyncio.run(go())


def test_control_alert_without_channel() -> None:
    channel = MagicMock(spec=discord.TextChannel)
    channel.send = AsyncMock()

    async def test(db: Database) -> None:
        prices = module(db, channel)
        table = RouteTable()
        module_routes(prices, table)
        async with TestClient(TestServer(control_app(table, KEY))) as http:
            assert (await http.post("/control/poe/alert", headers=AUTH, json=alert())).status == 200
            assert (await http.post("/control/poe/daily", headers=AUTH,
                                    json={"guild_id": GUILD, "game": "poe1", "league": "L", "up": [],
                                          "down": []})).status == 200
        channel.send.assert_not_awaited()

    with_db(test)


def test_control_alert_posts_with_mention() -> None:
    channel = MagicMock(spec=discord.TextChannel)
    channel.send = AsyncMock()

    async def test(db: Database) -> None:
        prices = module(db, channel)
        await prices.settings.update(GUILD, {"poe_channel": 77})
        table = RouteTable()
        module_routes(prices, table)
        async with TestClient(TestServer(control_app(table, KEY))) as http:
            assert (await http.post("/control/poe/alert", headers=AUTH, json=alert())).status == 200
        assert channel.send.await_args.kwargs["content"].startswith("<@42>")

    with_db(test)


def test_control_alert_rejects_bad_guild() -> None:
    async def test(db: Database) -> None:
        prices = module(db)
        for guild_id in (6, True, "5", None):
            request = SimpleNamespace(json=AsyncMock(return_value=alert(guild_id)))
            with pytest.raises(ApiError) as caught:
                await prices.alert(request)  # type: ignore[arg-type]
            assert caught.value.status == 400

    with_db(test)


def test_hub_client_from_env(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("BOT_CONTROL_KEY", KEY)
    monkeypatch.delenv("HUB_INTERNAL_URL", raising=False)
    assert HubClient.from_env() is None
    monkeypatch.setenv("HUB_INTERNAL_URL", "http://api:8000")
    assert HubClient.from_env() is not None
    monkeypatch.delenv("BOT_CONTROL_KEY")
    assert HubClient.from_env() is None


def test_hub_client_404_is_none() -> None:
    async def price(request: web.Request) -> web.Response:
        if request.headers.get("Authorization") != f"Bearer {KEY}":
            return web.json_response({"detail": "Schlüssel"}, status=401)
        if request.query["q"] == "kaputt":
            return web.json_response({"detail": "Fehler"}, status=500)
        if request.query["q"] != "Divine":
            return web.json_response({"detail": "Nichts gefunden"}, status=404)
        return web.json_response({"name": "Divine Orb"})

    async def go() -> None:
        app = web.Application()
        app.router.add_get("/api/internal/poe/price", price)
        async with TestServer(app) as server:
            hub = HubClient(str(server.make_url("")), KEY)
            try:
                assert await hub.get("/api/internal/poe/price", {"game": "poe1", "q": "nix"}) is None
                assert await hub.get("/api/internal/poe/price", {"game": "poe1", "q": "Divine"}) == \
                    {"name": "Divine Orb"}
                with pytest.raises(UserError, match="NexHub nicht erreichbar"):
                    await hub.get("/api/internal/poe/price", {"game": "poe1", "q": "kaputt"})
            finally:
                await hub.close()

    asyncio.run(go())
