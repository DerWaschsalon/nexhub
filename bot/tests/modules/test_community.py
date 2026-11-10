"""Community-Module: Levelsystem mit Sprachzeit, Starboard, Geburtstage."""

from __future__ import annotations

import asyncio
import datetime
import io
import tempfile
from pathlib import Path
from typing import Any
from unittest.mock import AsyncMock, MagicMock

import discord
import pytest
from nexcore import EventBus, Paths
from PIL import Image

from bot.core import BotContext
from bot.db import Database
from bot.errors import UserError
from bot.modules.community.birthdays import check_date
from bot.modules.community.levels.rankcard import HEIGHT, WIDTH, render_rank_card
from bot.modules.community.levels.store import level_from_xp, xp_for_level
from bot.modules.community.levels.voice import format_duration, qualifies
from bot.modules.community.starboard import STAR, Starboard, build_star_embed, star_count


def test_level_formula_and_conversion() -> None:
    assert (xp_for_level(0), xp_for_level(1), xp_for_level(10)) == (100, 155, 1100)
    assert level_from_xp(0) == (0, 0, 100)
    assert level_from_xp(100) == (1, 0, 155)  # genau die Schwelle: Level 1 erreicht
    assert level_from_xp(254) == (1, 154, 155)
    assert level_from_xp(-50) == (0, 0, 100)  # negative XP (von Hand überzogen) stürzen nicht ab


def test_rank_card_renders_valid_png() -> None:
    avatar = io.BytesIO()
    Image.new("RGBA", (64, 64), (10, 20, 30, 255)).save(avatar, format="PNG")
    image = Image.open(render_rank_card(avatar.getvalue(), "Test", level=3, rank=1, xp_into_level=50,
                                        xp_needed=200))
    assert image.format == "PNG" and image.size == (WIDTH, HEIGHT)
    # 0 nötige XP darf nicht durch null teilen
    assert Image.open(render_rank_card(avatar.getvalue(), "Test", 0, 1, 0, 0)).size == (WIDTH, HEIGHT)


def test_voice_time_rules() -> None:
    assert format_duration(90) == "1 Min." and format_duration(3661) == "1 Std. 1 Min."
    afk = MagicMock()
    channel = MagicMock(members=[MagicMock(bot=False), MagicMock(bot=False)])
    channel.guild.afk_channel = afk
    awake = MagicMock(bot=False, voice=MagicMock(self_deaf=False, deaf=False))
    assert qualifies(awake, channel)
    assert not qualifies(MagicMock(bot=False, voice=MagicMock(self_deaf=True, deaf=False)), channel)
    alone = MagicMock(members=[awake])
    alone.guild.afk_channel = afk
    assert not qualifies(awake, alone)  # allein zählt nicht


def test_birthday_dates() -> None:
    check_date(29, 2)  # Schaltjahr: erlaubt
    with pytest.raises(UserError):
        check_date(31, 4)


def star_message(author_id: int, star_users: list[int]) -> Any:
    async def users() -> Any:
        for uid in star_users:
            yield MagicMock(id=uid)

    reaction = MagicMock(emoji=STAR)
    reaction.users = users
    message = MagicMock(spec=discord.Message, id=42, content="hi", attachments=[], reactions=[reaction],
                        jump_url="https://discord.com/x", created_at=datetime.datetime.now(datetime.UTC))
    message.author = MagicMock(id=author_id)
    message.author.__str__.return_value = "Alice"
    message.channel = MagicMock(spec=discord.TextChannel, mention="#allgemein")
    return message


def test_star_count_ignores_author_and_embed_links_original() -> None:
    message = star_message(1, [1, 2, 3])  # Autor selbst und zwei andere
    assert asyncio.run(star_count(message)) == 2
    assert build_star_embed(message).fields[0].value == "[zur Nachricht](https://discord.com/x)"


def test_starboard_posts_from_threshold_on() -> None:
    async def go() -> None:
        with tempfile.TemporaryDirectory() as d:
            db = Database(Path(d) / "t.sqlite3")
            await db.connect()
            module = Starboard(BotContext(bus=EventBus(), paths=Paths("test"), db=db,
                                          client=MagicMock(spec=discord.Client)))
            board = MagicMock(spec=discord.TextChannel)
            board.guild.id = 1
            board.send = AsyncMock(return_value=MagicMock(id=999))
            message = star_message(1, [])
            await module.sync(message, 2, board, threshold=3)
            board.send.assert_not_awaited()  # unter der Schwelle
            await module.sync(message, 3, board, threshold=3)
            assert board.send.await_args is not None
            assert board.send.await_args.kwargs["content"] == f"{STAR} **3** | #allgemein"
            row = await db.fetchone("SELECT star_message_id FROM starboard WHERE message_id=?", (42,))
            assert row is not None and row["star_message_id"] == 999
            await db.close()

    asyncio.run(go())
