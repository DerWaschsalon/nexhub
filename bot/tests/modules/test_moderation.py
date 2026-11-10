"""Moderation: Automod-Regeln, Verwarnungen mit Strafe, Log über den Bus, Spamschutz-Ausnahmen."""

from __future__ import annotations

import asyncio
import tempfile
from collections.abc import Awaitable, Callable
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock

import discord
import pytest
from nexcore import EventBus, Paths

from bot.core import BotContext
from bot.core.moderation import LOG, QUIET_DELETE, WARN, LogEntry, WarnRequest, clip
from bot.db import Database
from bot.errors import UserError
from bot.modules.moderation.automod import caps_ratio, domain_allowed, violation
from bot.modules.moderation.automod.settings import AutomodSettings
from bot.modules.moderation.cleanup import MessageFilter
from bot.modules.moderation.log import ModerationLog
from bot.modules.moderation.warnings import Warnings


def test_automod_rules() -> None:
    assert caps_ratio("HALLO ZUSAMMEN WIE GEHTS") > 0.7 and caps_ratio("AB") == 0.0
    assert domain_allowed("sub.example.com", {"example.com"}) and not domain_allowed("evil.com", {"example.com"})
    assert violation("ganz normaler Text", AutomodSettings()) is None
    assert violation("ein böses-wort", AutomodSettings(automod_banned_words="böses-wort, x")) == "verbotenes Wort"
    assert violation("NUR GROSSBUCHSTABEN HIER", AutomodSettings(automod_caps=True)) == "zu viele Großbuchstaben"
    assert violation("😀😀😀", AutomodSettings(automod_emoji_limit=2)) == "Emoji-Spam"
    links = AutomodSettings(automod_link_filter=True, automod_allowed_domains="example.com")
    assert violation("https://evil.com/x", links) == "nicht erlaubter Link"
    assert violation("https://example.com/x", links) is None


def test_clip_and_message_filter() -> None:
    assert clip(None) == "*(kein Text)*" and clip("abc", 2) == "a…"
    pinned = MagicMock(pinned=True, author=MagicMock(id=1, bot=False))
    bot_message = MagicMock(pinned=False, author=MagicMock(id=2, bot=True))
    assert not MessageFilter(True, None, False).matches(pinned)
    assert MessageFilter(False, None, True).matches(bot_message)
    assert not MessageFilter(False, 1, False).matches(bot_message)


def with_modules(check: Callable[[BotContext, Database], Awaitable[None]]) -> None:
    async def go() -> None:
        with tempfile.TemporaryDirectory() as d:
            db = Database(Path(d) / "t.sqlite3")
            await db.connect()
            ctx = BotContext(bus=EventBus(), paths=Paths("test"), db=db, client=MagicMock(spec=discord.Client))
            await check(ctx, db)
            await db.close()

    asyncio.run(go())


def fake_member(guild: MagicMock, member_id: int) -> MagicMock:
    member = MagicMock(spec=discord.Member, id=member_id, bot=False, guild=guild, mention=f"<@{member_id}>")
    member.send = AsyncMock()
    member.timeout = AsyncMock()
    member.top_role.__lt__.return_value = True  # unter der Rolle des Bots
    return member


def test_warnings_count_log_and_punish_at_threshold() -> None:
    async def check(ctx: BotContext, db: Database) -> None:
        module = Warnings(ctx)
        await module.start()
        logged: list[LogEntry] = []
        ctx.bus.on(LOG, logged.append)
        guild = MagicMock(spec=discord.Guild, id=1)
        guild.name = "Waschsalon"
        member = fake_member(guild, 5)
        await db.set(1, "warn_threshold", 2)
        await db.set(1, "warn_action", "timeout")
        await ctx.bus.emit(WARN, WarnRequest(guild, member, MagicMock(id=9, mention="<@9>"), "Automod: Spam"))
        assert await module.warn(guild, member, MagicMock(id=9, mention="<@9>"), "nochmal") == 2
        member.timeout.assert_awaited_once()  # Schwelle erreicht
        assert [e.embed.title for e in logged][:2] == ["⚠️ Verwarnung Nr. 1", "⚠️ Verwarnung Nr. 2"]
        with pytest.raises(UserError):
            await module.store.delete(1, 999)

    with_modules(check)


def test_log_writes_events_and_skips_quiet_deletes() -> None:
    async def check(ctx: BotContext, db: Database) -> None:
        module = ModerationLog(ctx)
        await module.start()
        channel = MagicMock(spec=discord.TextChannel)
        channel.send = AsyncMock()
        guild = MagicMock(spec=discord.Guild, id=1)
        guild.get_channel.return_value = channel
        await db.set(1, "log_channel", 77)
        await ctx.bus.emit(LOG, LogEntry(guild, discord.Embed(title="Test")))
        channel.send.assert_awaited_once()
        await ctx.bus.emit(QUIET_DELETE, [42])
        message = MagicMock(spec=discord.Message, id=42, guild=guild)
        await module.on_message_delete(message)
        channel.send.assert_awaited_once()  # leise gelöscht: kein zweiter Eintrag
        assert 42 not in module.quiet

    with_modules(check)
