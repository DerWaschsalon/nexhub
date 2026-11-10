"""Offline-Tests rund um den Bot als Ganzes: Befehle laden, Datenbank, /setup, Steuer-API-Seiten."""

from __future__ import annotations

import asyncio
import tempfile
from pathlib import Path
from unittest.mock import MagicMock

import discord
import pytest

from bot.__main__ import Bot
from bot.db import Database


def check_hub_pages(pages):
    """Menü des Hubs: jede Seite einmal, Formulare zeigen auf echte Bereiche, Aktionen sind auffindbar."""
    from bot.cogs.control import SECTIONS
    from bot.hubpages import GROUPS, Actions, Form, Status, Table

    ids = [p.id for p in pages]
    assert len(ids) == len(set(ids)), ids
    for want in ("", "allgemein", "giveaways", "server", "moderation", "musik", "benachrichtigungen",
                 "erinnerungen", "geburtstage", "aion"):
        assert want in ids, want
    for p in pages:
        assert p.group in GROUPS, (p.id, p.group)
        assert p.custom or p.blocks, p.id
        block_ids = [getattr(b, "id", None) or b.section for b in p.blocks]
        assert len(block_ids) == len(set(block_ids)), (p.id, block_ids)
        for b in p.blocks:
            if isinstance(b, Form):
                assert b.section in SECTIONS, (p.id, b.section)
                continue
            actions = [*b.actions] + ([b.create] if isinstance(b, Table) and b.create else [])
            assert isinstance(b, (Table, Status, Actions))
            for a in actions:
                assert p.action(b.id, a.id) is a
                assert len({f.key for f in a.fields}) == len(a.fields), (p.id, a.id)


def test_all_commands_register():
    async def go():
        with tempfile.TemporaryDirectory() as d:
            bot = Bot(Database(Path(d) / "t.sqlite3"), sync=False)
            await bot.setup_hook()
            names = sorted(c.qualified_name for c in bot.tree.walk_commands())
            pages = bot.get_cog("Control").all_pages()
            await bot.modules.stop()
            await bot.db.close()
            return names, pages
    names, pages = asyncio.run(go())
    check_hub_pages(pages)
    for expected in ["play", "radio", "skip", "stop", "warteschlange", "lautstaerke", "wiederholen",
                     "setup aendern", "setup anzeigen", "setup temp-voice", "setup panel", "setup management-kanal",
                     "setup verifizierung", "setup regeln-text", "rollen-panel", "timeout",
                     "warn", "warnungen", "warnung-loeschen", "kick", "ban", "unban",
                     "erinnere", "erinnerungen", "erinnerung-loeschen", "aion", "dungeon-rangliste",
                     "ticket-panel", "umfrage", "geburtstag-setzen", "geburtstag-loeschen", "geburtstag",
                     "embed-erstellen", "befehl-erstellen", "befehl-loeschen", "befehle",
                     "ankuendigung-erstellen", "ankuendigungen", "ankuendigung-loeschen",
                     "sprachzeit", "giveaway-erstellen", "giveaway-reroll",
                     "rang", "rangliste", "level-xp-geben", "level-belohnung",
                     "level-kanal-ohne-xp", "level-rolle-ohne-xp",
                     "server", "server-neustart", "server-update",
                     "vc name", "vc sperren", "aufraeumen nachrichten", "aufraeumen bots", "aufraeumen bericht"]:
        assert expected in names, expected
    # Discord: höchstens 100 Top-Level-Befehle, Namen kleingeschrieben, ≤ 32 Zeichen
    for n in names:
        for part in n.split():
            assert part == part.lower() and len(part) <= 32


def test_db_roundtrip():
    async def go():
        with tempfile.TemporaryDirectory() as d:
            db = Database(Path(d) / "t.sqlite3")
            await db.connect()
            await db.set(1, "log_channel", 42)
            await db.set(1, "antispam", False)
            await db.add_temp_channel(5, 1, 9)
            await db.close()
            db2 = Database(Path(d) / "t.sqlite3")
            await db2.connect()
            r = (db2.get_int(1, "log_channel"), db2.get_bool(1, "antispam", True),
                 await db2.temp_channel_owner(5))
            await db2.set(1, "log_channel", None)
            r += (db2.get(1, "log_channel"),)
            await db2.close()
            return r
    assert asyncio.run(go()) == (42, False, 9, None)


def test_settings_panel_persistent_has_stable_custom_ids():
    from bot.cogs.settings import SettingsPanel
    from bot.forms import SECTIONS

    pages = sum(len(section.groups()) for section in SECTIONS.values())
    cog = type("FakeCog", (), {})()
    view = SettingsPanel(cog, guild=object(), persistent=True)
    assert len(view.children) == pages + 2  # Seiten, Verifizierung, Benachrichtigungen; kein Schließen
    assert all(item.custom_id for item in view.children)
    assert len({item.custom_id for item in view.children}) == len(view.children)

    ephemeral = SettingsPanel(cog, guild=object(), persistent=False)
    assert len(ephemeral.children) == pages + 3  # inkl. Schließen


def test_role_can_view():

    from bot.cogs.control import role_can_view

    class FakeChannel:
        def __init__(self, overwrites):
            self._ow = overwrites

        def overwrites_for(self, target):
            return self._ow.get(target, discord.PermissionOverwrite())

    class FakeRole:
        def __init__(self, perms):
            self.permissions = perms

    everyone = FakeRole(discord.Permissions(view_channel=True))
    role = FakeRole(discord.Permissions.none())

    # Kein Overwrite: @everyone darf sehen (Basisrecht), also auch diese Rolle
    assert role_can_view(FakeChannel({}), role, everyone) is True

    # @everyone per Overwrite ausgeschlossen, Rolle ohne eigenes Overwrite -> nicht sichtbar
    ch = FakeChannel({everyone: discord.PermissionOverwrite(view_channel=False)})
    assert role_can_view(ch, role, everyone) is False

    # @everyone ausgeschlossen, Rolle aber explizit erlaubt -> rollen-spezifisch gewinnt
    ch = FakeChannel({
        everyone: discord.PermissionOverwrite(view_channel=False),
        role: discord.PermissionOverwrite(view_channel=True),
    })
    assert role_can_view(ch, role, everyone) is True


def test_panel_regex():
    import re
    pat = re.compile(r"(?:(<a?:\w+:\d+>|[^\x00-\x7F\s]+)\s*)?<@&(\d+)>")
    got = [(m.group(1), m.group(2)) for m in pat.finditer("🎮 <@&1> und <@&2> <:aion:99> <@&3>")]
    assert got == [("🎮", "1"), (None, "2"), ("<:aion:99>", "3")]


def test_every_panel_page_fits_discord_limits():
    """Jede erzeugte Seite muss sich bauen lassen (Discord: 5 Zeilen, je Zeile eine Auswahl oder
    5 Knöpfe) und stabile custom_ids haben, in beiden Verifizierungs-Zuständen."""
    from pathlib import Path

    from nexcore import EventBus, Paths

    from bot.cogs.settings import EXTRAS, SettingsPanel
    from bot.core import BotContext
    from bot.db import Database
    from bot.forms import SECTIONS
    from bot.modules.server.verification import Verification
    from bot.modules.server.verification.panel import Flow
    from bot.panel import FieldPage

    cog = type("FakeCog", (), {})()
    cog.db = Database(Path("/tmp/_unused_panel_page_test.sqlite3"))
    cog.bot = object()
    guild = type("G", (), {"id": 1})()
    panel = SettingsPanel(cog, guild, persistent=True)

    async def back(_interaction):
        return None

    for section in SECTIONS.values():
        for index, (group, _fields) in enumerate(section.groups()):
            extra = EXTRAS.get((section.id, group))
            page = FieldPage(cog.bot, cog.db, guild, section, index, back,
                             extras=(extra(panel),) if extra else (), persistent=True)
            assert all(item.custom_id for item in page.children), (section.id, group)
            assert page.embed().title

    verification = Verification(BotContext(bus=EventBus(), paths=Paths("test"), db=cog.db, client=MagicMock()))
    for active in (True, False):
        cog.db._settings[1] = {"verify_active": "1" if active else "0"}
        view = Flow(verification, guild, True, back).menu()
        assert all(item.custom_id for item in view.children)


def test_setup_change_parses_input():
    import pytest

    from bot.cogs.settings import parse_input
    from bot.errors import UserError
    from bot.forms import find_field

    def field(key):
        return find_field(key)[1]

    assert parse_input(field("log_channel"), "<#123456789012345678>") == "123456789012345678"
    assert parse_input(field("log_channel"), "") is None
    assert parse_input(field("level_no_xp_roles"), "<@&123456789012345678> 223456789012345678") == [
        "123456789012345678", "223456789012345678"]
    assert parse_input(field("antispam"), "Aus") is False
    assert parse_input(field("warn_threshold"), "") == 0
    assert parse_input(field("starboard_threshold"), "5") == 5
    with pytest.raises(UserError):
        parse_input(field("antispam"), "vielleicht")
    with pytest.raises(UserError):
        parse_input(field("log_channel"), "#allgemein")


def test_hub_action_values():
    """Werte aus dem Hub: Pflichtfelder, Grenzen, Auswahl und ausgeblendete Felder (show_if)."""

    from bot.hubpages import ApiError, Field, action_values

    class Ch:
        def __init__(self, cid, kind):
            self.id, self.type, self.name = cid, kind, f"k{cid}"

    class Guild:
        channels = {1: Ch(1, discord.ChannelType.text), 2: Ch(2, discord.ChannelType.voice)}
        members = {5: "Mitglied 5"}

        def get_channel(self, i):
            return self.channels.get(i)

        def get_member(self, i):
            return self.members.get(i)

        def get_role(self, i):
            return None

    g = Guild()
    fields = (
        Field("kind", "choice", "Dienst", default="a", options=(("a", "A"), ("b", "B"))),
        Field("src_a", "text", "Quelle A", required=True, show_if=("kind", ("a",))),
        Field("src_b", "text", "Quelle B", required=True, show_if=("kind", ("b",))),
        Field("ev", "multi", "Ereignisse", options=("x", "y")),
        Field("n", "int", "Anzahl", default=1, min=1, max=3),
        Field("ch", "channel", "Kanal"),
        Field("who", "member", "Mitglied"),
    )
    v = action_values(g, fields, {"kind": "a", "src_a": " repo ", "ev": ["y", "y"], "n": 2, "ch": "1", "who": "5"})
    assert v["src_a"] == "repo" and "src_b" not in v and v["ev"] == ["y"] and v["n"] == 2
    assert v["ch"] is g.channels[1] and v["who"] == "Mitglied 5"
    assert action_values(g, fields, {"kind": "a", "src_a": "r"})["n"] == 1  # Standardwert
    for bad in ({"kind": "b", "src_a": "r"},           # src_b ist Pflicht, src_a zählt nicht
                {"kind": "c", "src_a": "r"},           # unbekannte Auswahl
                {"kind": "a", "src_a": "r", "n": 4},   # über max
                {"kind": "a", "src_a": "r", "ev": ["z"]},
                {"kind": "a", "src_a": "r", "ch": "2"},  # Sprachkanal statt Textkanal
                {"kind": "a", "src_a": "r", "who": "9"}):
        with pytest.raises(ApiError):
            action_values(g, fields, bad)


