"""community.bump: Bestätigung erkennen, nach dem Cooldown einmal erinnern."""

from __future__ import annotations

import asyncio
import tempfile
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock

import discord
from nexcore import EventBus, Paths

from bot.core import BotContext
from bot.db import Database
from bot.modules.community.bump import (
    BUMP_INTERVAL_S,
    DISBOARD_BOT_ID,
    REMINDER,
    Bump,
    is_bump_confirmation,
    is_due,
)
from bot.modules.community.bump.settings import BumpSettings


def fake_message(author_id: int, embeds: list[discord.Embed]) -> discord.Message:
    return type("M", (), {"author": type("A", (), {"id": author_id})(), "embeds": embeds})()  # type: ignore[no-any-return]


def test_bump_confirmation_detection() -> None:
    success = discord.Embed(description="Bump done! :thumbsup: Check it out on disboard.org!")
    cooldown = discord.Embed(description="Please wait another 23 minutes before bumping again.")
    assert is_bump_confirmation(fake_message(DISBOARD_BOT_ID, [success])) is True
    assert is_bump_confirmation(fake_message(DISBOARD_BOT_ID, [cooldown])) is False
    assert is_bump_confirmation(fake_message(123, [success])) is False  # anderer Autor
    assert is_bump_confirmation(fake_message(DISBOARD_BOT_ID, [])) is False  # kein Embed


def test_due_only_once_after_cooldown() -> None:
    assert not is_due(BumpSettings(), 0)
    assert not is_due(BumpSettings(bump_last=0), BUMP_INTERVAL_S - 1)
    assert is_due(BumpSettings(bump_last=0), BUMP_INTERVAL_S)
    assert not is_due(BumpSettings(bump_last=0, bump_reminded=True), BUMP_INTERVAL_S)


def test_reminder_pings_role_once() -> None:
    async def go() -> None:
        with tempfile.TemporaryDirectory() as d:
            db = Database(Path(d) / "t.sqlite3")
            await db.connect()
            await db.set(1, "bump_channel", 42)
            await db.set(1, "bump_role", 7)
            await db.set(1, "bump_last", 0)

            channel = MagicMock(spec=discord.TextChannel)
            channel.send = AsyncMock()
            channel.guild.get_role.return_value = type("R", (), {"mention": "<@&7>"})()
            client = MagicMock(spec=discord.Client)
            client.get_channel.return_value = channel

            module = Bump(BotContext(bus=EventBus(), paths=Paths("test"), db=db, client=client))
            await module.remind_due()
            await module.remind_due()  # zweiter Takt: schon erinnert
            channel.send.assert_awaited_once()
            assert channel.send.await_args.args[0] == f"<@&7> {REMINDER}"
            assert db.get(1, "bump_reminded") == "1"
            await db.close()

    asyncio.run(go())
