"""GuildSettings liest und schreibt dieselben Einträge wie die alten Cogs (db.get/db.set)."""

from __future__ import annotations

import asyncio
import tempfile
from collections.abc import Awaitable, Callable
from pathlib import Path

import pytest
from pydantic import BaseModel, ValidationError

from bot.core import GuildSettings, IdList
from bot.db import Database


class Example(BaseModel):
    channel: int | None = None
    on: bool = True
    limit: int = 3
    roles: IdList = []
    text: str = ""


def with_db(check: Callable[[Database], Awaitable[None]]) -> None:
    async def go() -> None:
        with tempfile.TemporaryDirectory() as d:
            db = Database(Path(d) / "t.sqlite3")
            await db.connect()
            await check(db)
            await db.close()

    asyncio.run(go())


def test_reads_values_written_the_old_way() -> None:
    async def check(db: Database) -> None:
        await db.set(1, "channel", 42)
        await db.set(1, "on", False)
        await db.set(1, "limit", 7)
        await db.set(1, "roles", "11,22,keine-id")
        value = GuildSettings(db, Example).get(1)
        assert value == Example(channel=42, on=False, limit=7, roles=[11, 22])
        assert GuildSettings(db, Example).get(2) == Example()  # anderer Server: Standard

    with_db(check)


def test_bad_value_falls_back_per_field() -> None:
    async def check(db: Database) -> None:
        await db.set(1, "limit", "viele")
        await db.set(1, "channel", 42)
        assert GuildSettings(db, Example).get(1) == Example(channel=42)

    with_db(check)


def test_update_writes_like_db_set() -> None:
    async def check(db: Database) -> None:
        settings = GuildSettings(db, Example)
        await settings.update(1, {"on": False, "roles": [5, 6], "channel": None})
        assert db.get(1, "on") == "0" and db.get(1, "roles") == "5,6" and db.get(1, "channel") is None
        assert settings.guilds_with("roles") == [1]
        with pytest.raises(ValidationError):
            await settings.update(1, {"limit": "viele"})
        assert db.get(1, "limit") is None  # nichts gespeichert

    with_db(check)
