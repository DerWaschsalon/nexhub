"""Verifizierung: Knopf „Regeln akzeptiert“ vergibt Rolle und Autorolle, Text-Prüfung."""

from __future__ import annotations

import asyncio
import tempfile
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock

import discord
import pytest
from nexcore import EventBus, Paths

from bot.core import BotContext
from bot.db import Database
from bot.errors import UserError
from bot.modules.server.verification import Verification


def make_member(roles: list[discord.Role]) -> MagicMock:
    member = MagicMock(spec=discord.Member)
    member.id = 5
    member.roles = roles
    member.add_roles = AsyncMock()
    return member


def make_role(role_id: int, position: int) -> MagicMock:
    role = MagicMock(spec=discord.Role)
    role.id = role_id
    role.managed = False
    role.is_default.return_value = False
    role.__lt__ = lambda self, other: position < 100
    return role


def test_accept_gives_role_and_autorole() -> None:
    async def run() -> None:
        with tempfile.TemporaryDirectory() as d:
            db = Database(Path(d) / "t.sqlite3")
            await db.connect()
            module = Verification(BotContext(bus=EventBus(), paths=Paths("test"), db=db,
                                             client=MagicMock(spec=discord.Client)))
            verified, autorole = make_role(10, 5), make_role(11, 4)
            guild = MagicMock(spec=discord.Guild)
            guild.id = 1
            guild.get_role = {10: verified, 11: autorole}.get
            guild.me.top_role = make_role(99, 100)
            guild.me.guild_permissions.manage_roles = True

            member = make_member([])
            member.guild = guild
            assert await module.accept(member) == "Verifizierung ist nicht mehr eingerichtet."

            await module.settings.update(1, {"verify_role": 10, "verify_active": True})
            await db.set(1, "autorole", 11)
            assert (await module.accept(member)).startswith("✅")
            given = [call.args[0] for call in member.add_roles.await_args_list]
            assert given == [verified, autorole]

            member.roles = [verified]
            assert await module.accept(member) == "Du bist schon verifiziert."
            await db.close()

    asyncio.run(run())


def test_set_text_checks_length_and_panel() -> None:
    db = MagicMock(spec=Database)
    db.get.return_value = None
    module = Verification(BotContext(bus=EventBus(), paths=Paths("test"), db=db,
                                     client=MagicMock(spec=discord.Client)))
    guild = MagicMock(spec=discord.Guild)
    guild.id = 1
    guild.get_channel.return_value = None
    with pytest.raises(UserError, match="Kein Text"):
        asyncio.run(module.set_text(guild, "   "))
    with pytest.raises(UserError, match="4096"):
        asyncio.run(module.set_text(guild, "x" * 5000))
    with pytest.raises(UserError, match="Regeln-Panel"):
        asyncio.run(module.set_text(guild, "Neue Regeln"))
