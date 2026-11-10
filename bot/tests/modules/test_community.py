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


def test_reminder_parsing() -> None:
    from zoneinfo import ZoneInfo

    from bot.core.when import parse_when

    tz = ZoneInfo("Europe/Berlin")
    now = datetime.datetime(2026, 10, 14, 12, 0, tzinfo=tz)

    assert parse_when("2h", now) == now + datetime.timedelta(hours=2)
    assert parse_when("30m", now) == now + datetime.timedelta(minutes=30)
    assert parse_when("1d2h", now) == now + datetime.timedelta(days=1, hours=2)

    assert parse_when("18:30", now) == now.replace(hour=18, minute=30)
    # schon vorbei -> morgen
    assert parse_when("08:00", now) == now.replace(hour=8, minute=0) + datetime.timedelta(days=1)

    assert parse_when("24.12. 18:00", now) == datetime.datetime(2026, 12, 24, 18, 0, tzinfo=tz)
    # schon vorbei -> nächstes Jahr
    assert parse_when("1.1. 10:00", now) == datetime.datetime(2027, 1, 1, 10, 0, tzinfo=tz)
    # Jahr explizit, kein Shift
    assert parse_when("24.12.2025 18:00", now) == datetime.datetime(2025, 12, 24, 18, 0, tzinfo=tz)

    with pytest.raises(Exception):
        parse_when("irgendwann", now)


def test_poll_answer_parsing() -> None:
    import pytest as _pytest

    from bot.errors import UserError
    from bot.modules.community.polls import parse_answers

    assert parse_answers("Ja | Nein") == ["Ja", "Nein"]
    assert parse_answers(" A | B | C ") == ["A", "B", "C"]

    with _pytest.raises(UserError):
        parse_answers("Nur eine Antwort")  # weniger als 2
    with _pytest.raises(UserError):
        parse_answers("|".join(f"A{i}" for i in range(11)))  # mehr als 10
    with _pytest.raises(UserError):
        parse_answers("x" * 56 + "|Nein")  # einzelne Antwort zu lang


def test_giveaway_embed_running_and_ended() -> None:
    import time

    from bot.modules.community.giveaways import build_giveaway_embed

    running = build_giveaway_embed("Steam-Key", 2, time.time() + 3600, host_id=42)
    assert running.title == "🎉 Giveaway"
    assert any(f.name == "Gestartet von" and f.value == "<@42>" for f in running.fields)

    ended_with_winners = build_giveaway_embed("Steam-Key", 2, time.time(), None, ended=True, winner_ids=[1, 2])
    assert ended_with_winners.title == "🎉 Giveaway beendet"
    winners = str(ended_with_winners.fields[0].value)
    assert "<@1>" in winners and "<@2>" in winners

    ended_no_entries = build_giveaway_embed("Steam-Key", 2, time.time(), None, ended=True, winner_ids=[])
    assert ended_no_entries.fields[0].value == "Niemand hat teilgenommen"


def test_giveaway_pick_winners_respects_count_and_uses_entries() -> None:
    import tempfile
    from pathlib import Path

    from bot.db import Database
    from bot.modules.community.giveaways.store import GiveawayStore

    async def go() -> Any:
        with tempfile.TemporaryDirectory() as d:
            db = Database(Path(d) / "t.sqlite3")
            await db.connect()
            for uid in (1, 2, 3):
                await db.execute("INSERT INTO giveaway_entries (message_id, user_id) VALUES (?, ?)", (99, uid))

            store = GiveawayStore(db)

            winners = await store.pick_winners(99, 2)
            assert len(winners) == 2
            assert set(winners) <= {1, 2, 3}

            no_entries = await store.pick_winners(100, 2)
            assert no_entries == []

            await db.close()

    asyncio.run(go())


def test_hub_giveaway_page() -> None:
    """Giveaway-Seite: Zeilen aus der DB, Schalter für die Aktionen je Zeile."""
    from unittest.mock import MagicMock

    from nexcore import EventBus, Paths

    from bot.core import BotContext
    from bot.hubpages import Ctx, page_out
    from bot.modules.community.giveaways import Giveaways

    class Guild:
        id = 1
        me = None

        def get_channel(self, i: int) -> None:
            return None

        def get_member(self, i: int) -> None:
            return None

    async def go() -> Any:
        with tempfile.TemporaryDirectory() as d:
            db = Database(Path(d) / "t.sqlite3")
            await db.connect()
            module = Giveaways(BotContext(bus=EventBus(), paths=Paths("test"), db=db, client=MagicMock()))
            await db.execute("INSERT INTO giveaways VALUES (11, 1, 5, 7, 'Nitro', 1, 2000000000, 0)")
            await db.execute("INSERT INTO giveaways VALUES (12, 1, 5, 7, 'Alt', 2, 1000, 1)")
            await db.execute("INSERT INTO giveaway_entries VALUES (11, 3)")
            guild: Any = Guild()  # nachgebauter Server, nur was die Seite liest
            out = await page_out(Ctx(None, guild), module.pages()[0], lambda s: {})
            await db.close()
            return out

    out = asyncio.run(go())
    table = out["blocks"][0]
    assert table["type"] == "table" and table["create"]["id"] == "create"
    first, second = table["rows"]
    assert (first["prize"], first["entries"], first["active"]) == ("Nitro", 1, True)
    assert (second["prize"], second["ended"], second["state"]) == ("Alt", True, "beendet")
    assert {a["id"]: a["when"] for a in table["actions"]} == {"end": "active", "reroll": "ended", "delete": ""}


