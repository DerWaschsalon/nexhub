"""Server-Module: Begrüßung, Rollen-Panel, Zähler, Ankündigungen, eigene Befehle, Embeds."""

from __future__ import annotations

import asyncio
import tempfile
import time
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock

import discord
import pytest
from nexcore import EventBus, Paths

from bot.core import BotContext
from bot.db import Database
from bot.errors import UserError
from bot.modules.server.announcements import Announcements
from bot.modules.server.counters import bots_channel_name, member_channel_name
from bot.modules.server.custom_commands import CommandStore, clean_name, command_name, render
from bot.modules.server.embeds import build_embed, parse_colour
from bot.modules.server.welcome import welcome_text


def context(db: Database, client: discord.Client) -> BotContext:
    return BotContext(bus=EventBus(), paths=Paths("test"), db=db, client=client)


async def open_db(folder: str) -> Database:
    db = Database(Path(folder) / "t.sqlite3")
    await db.connect()
    return db


def test_counter_names() -> None:
    bots = [MagicMock(bot=True), MagicMock(bot=True), MagicMock(bot=False)]
    guild = MagicMock(member_count=123, members=bots)
    assert member_channel_name(guild) == "👥 Mitglieder: 123"
    assert bots_channel_name(guild) == "🤖 Bots: 2"


def test_welcome_text_placeholders() -> None:
    member = MagicMock(mention="<@1>", display_name="Ana_", guild=MagicMock(member_count=7))
    member.guild.name = "Waschsalon"
    text = welcome_text("Hi {user} ({name}) auf {server}, Nr. {anzahl}", member)
    assert text == "Hi <@1> (Ana\\_) auf Waschsalon, Nr. 7"


def test_embed_building() -> None:
    assert parse_colour(None) == discord.Colour.blurple()
    assert parse_colour("#5865F2") == discord.Colour(0x5865F2)
    with pytest.raises(UserError):
        parse_colour("nicht-hex")
    with pytest.raises(UserError):
        build_embed("", "", "", "")
    assert build_embed("Titel", "", "", "https://example.com/x.png").image.url == "https://example.com/x.png"


def test_custom_command_names_and_rendering() -> None:
    member = MagicMock(mention="<@1>")
    guild = MagicMock()
    guild.name = "Der Waschsalon"
    text = render("Hallo {user}, willkommen auf {server}!", member, guild)
    assert text == "Hallo <@1>, willkommen auf Der Waschsalon!"
    assert clean_name("!Regeln ") == "regeln"
    with pytest.raises(UserError):
        clean_name("mit leerzeichen")
    assert command_name("!regeln bitte") == "regeln" and command_name("hallo") == "" and command_name("!") == ""


def test_custom_command_store() -> None:
    async def go() -> None:
        with tempfile.TemporaryDirectory() as d:
            db = await open_db(d)
            store = CommandStore(db)
            await store.put(1, "!Info", "Text")
            assert await store.response(1, "info") == "Text"
            await store.delete(1, "info")
            with pytest.raises(UserError):
                await store.delete(1, "info")
            await db.close()

    asyncio.run(go())


def test_announcement_due_rows_get_rescheduled() -> None:
    async def go() -> None:
        with tempfile.TemporaryDirectory() as d:
            db = await open_db(d)
            now = time.time()
            module = Announcements(context(db, MagicMock(spec=discord.Client)))
            due_id = await module.store.add(1, 2, "Hallo!", 30)
            later_id = await module.store.add(1, 2, "Später", 30)
            await db.execute("UPDATE scheduled SET next_run=? WHERE id=?", (now + 10_000, later_id))

            channel = MagicMock(spec=discord.TextChannel)
            channel.send = AsyncMock()
            module.client.get_channel.return_value = channel  # type: ignore[attr-defined]
            await module.post_due()

            channel.send.assert_awaited_once_with("Hallo!")
            due = await db.fetchone("SELECT next_run FROM scheduled WHERE id=?", (due_id,))
            later = await db.fetchone("SELECT next_run FROM scheduled WHERE id=?", (later_id,))
            assert due is not None and due["next_run"] > now  # neu geplant
            assert later is not None and later["next_run"] == now + 10_000  # unverändert
            await db.close()

    asyncio.run(go())
