"""Steuer-API für den NexHub (bot/cogs/control.py) mit nachgebautem Discord-Server."""
import asyncio
import json
import tempfile
from pathlib import Path
from types import SimpleNamespace

import discord
from aiohttp.test_utils import TestClient, TestServer

from bot.cogs.control import Control
from bot.db import Database

KEY = "k" * 32
AUTH = {"Authorization": f"Bearer {KEY}"}
GUILD = 900000000000000001  # größer als 2^53: muss als String durch die API


class FakeRole:
    def __init__(self, rid, name, position, *, default=False, managed=False):
        self.id, self.name, self.position = rid, name, position
        self.managed = managed
        self._default = default
        self.color = discord.Colour(0)
        self.permissions = discord.Permissions(view_channel=default)

    def is_default(self):
        return self._default

    def __lt__(self, other):
        return self.position < other.position

    def __ge__(self, other):
        return self.position >= other.position


class FakeChannel:
    def __init__(self, cid, name, ctype, position, category=None):
        self.id, self.name, self.type, self.position, self.category = cid, name, ctype, position, category
        self.overwrites: dict = {}
        self.channels: list = []

    def overwrites_for(self, target):
        return self.overwrites.get(target, discord.PermissionOverwrite())

    async def set_permissions(self, role, *, view_channel, reason):
        self.overwrites[role] = discord.PermissionOverwrite(view_channel=view_channel)
        self.last_reason = reason


def fake_guild():
    everyone = FakeRole(GUILD, "@everyone", 0, default=True)
    member = FakeRole(GUILD + 10, "Mitglied", 1)
    bot_role = FakeRole(GUILD + 11, "TheWashBot", 5, managed=True)
    admin = FakeRole(GUILD + 12, "Admin", 9)
    cat = FakeChannel(GUILD + 20, "Allgemein", discord.ChannelType.category, 0)
    text = FakeChannel(GUILD + 21, "chat", discord.ChannelType.text, 1, cat)
    voice = FakeChannel(GUILD + 22, "Lobby", discord.ChannelType.voice, 2, cat)
    cat.channels = [text, voice]
    channels = [cat, text, voice]
    roles = [everyone, member, bot_role, admin]
    return SimpleNamespace(
        id=GUILD, name="Testserver", icon=None, member_count=3, members=[], default_role=everyone,
        channels=channels, categories=[cat], roles=roles, me=SimpleNamespace(top_role=bot_role),
        get_channel=lambda i: next((c for c in channels if c.id == i), None),
        get_role=lambda i: next((r for r in roles if r.id == i), None),
    )


def run(test):
    """Startet die Steuer-API mit echter Datenbank und ruft `test(client, db, guild)` auf."""
    async def go():
        with tempfile.TemporaryDirectory() as d:
            db = Database(Path(d) / "t.sqlite3")
            await db.connect()
            guild = fake_guild()
            bot = SimpleNamespace(db=db, guilds=[guild], get_guild=lambda i: guild if i == GUILD else None,
                                  get_cog=lambda name: None, cogs={}, user=None, latency=float("nan"),
                                  is_ready=lambda: True)
            cog = Control(bot)
            cog.key = KEY
            async with TestClient(TestServer(cog.make_app())) as client:
                await test(client, db, guild)
            await db.close()
    asyncio.run(go())


async def call(client, method, path, body=None, status=200):
    resp = await client.request(method, path, headers=AUTH, json=body)
    assert resp.status == status, await resp.text()
    return None if status == 204 else await resp.json()


def test_key_required():
    async def test(client, db, guild):
        assert (await client.get("/control/status")).status == 401
        bad = await client.get("/control/status", headers={"Authorization": "Bearer falsch"})
        assert bad.status == 401
        assert (await call(client, "GET", "/control/status"))["guild"]["id"] == str(GUILD)
    run(test)


def test_guild_ids_are_strings_and_roles_filtered():
    async def test(client, db, guild):
        data = await call(client, "GET", "/control/guild")
        assert data["id"] == str(GUILD)
        assert [c["kind"] for c in data["channels"]] == ["category", "text", "voice"]
        assert data["channels"][1]["category"] == str(GUILD + 20)
        # Kanäle ohne Kategorie zuerst, danach Kategorie für Kategorie (position zählt nur darin)
        loose = FakeChannel(GUILD + 30, "ohne", discord.ChannelType.text, 5)
        guild.channels.append(loose)
        data = await call(client, "GET", "/control/guild")
        assert [c["name"] for c in data["channels"]] == ["ohne", "Allgemein", "chat", "Lobby"]
        # @everyone und Integrationsrollen fehlen, Admin steht über dem Bot
        assert [(r["name"], r["assignable"]) for r in data["roles"]] == [("Admin", False), ("Mitglied", True)]
    run(test)


def test_section_save_validates_before_writing():
    async def test(client, db, guild):
        sections = {s["id"]: s for s in await call(client, "GET", "/control/sections")}
        antispam = next(f for f in sections["allgemein"]["fields"] if f["key"] == "antispam")
        assert antispam["value"] is True  # Standard an, ohne gespeicherten Wert

        values = {"log_channel": str(GUILD + 21), "antispam": False, "welcome_text": "  Hallo {user}  "}
        out = await call(client, "PUT", "/control/sections/allgemein", {"values": values})
        assert db.get(GUILD, "log_channel") == str(GUILD + 21)
        assert db.get(GUILD, "antispam") == "0"
        assert db.get(GUILD, "welcome_text") == "Hallo {user}"
        assert next(f for f in out["fields"] if f["key"] == "log_channel")["value"] == str(GUILD + 21)

        # Sprachkanal als Textkanal: alles bleibt beim Alten, auch das gültige Feld davor
        bad = {"antispam": True, "log_channel": str(GUILD + 22)}
        await call(client, "PUT", "/control/sections/allgemein", {"values": bad}, status=400)
        assert db.get(GUILD, "antispam") == "0"
        await call(client, "PUT", "/control/sections/allgemein", {"values": {"gibtsnicht": 1}}, status=400)
        await call(client, "PUT", "/control/sections/gibtsnicht", {"values": {}}, status=404)
    run(test)


def test_section_int_zero_and_warn_action():
    async def test(client, db, guild):
        await call(client, "PUT", "/control/sections/verwarnungen",
                   {"values": {"warn_threshold": 3, "warn_action": "kick"}})
        assert (db.get(GUILD, "warn_threshold"), db.get(GUILD, "warn_action")) == ("3", "kick")
        await call(client, "PUT", "/control/sections/verwarnungen", {"values": {"warn_threshold": 0}})
        assert (db.get(GUILD, "warn_threshold"), db.get(GUILD, "warn_action")) == (None, None)
        await call(client, "PUT", "/control/sections/verwarnungen", {"values": {"warn_action": "bannen"}}, status=400)
        await call(client, "PUT", "/control/sections/community", {"values": {"starboard_threshold": 0}}, status=400)
    run(test)


def test_section_id_lists():
    async def test(client, db, guild):
        values = {"level_no_xp_roles": [str(GUILD + 10), str(GUILD + 10)], "level_no_xp_channels": []}
        out = await call(client, "PUT", "/control/sections/level", {"values": values})
        assert db.get(GUILD, "level_no_xp_roles") == str(GUILD + 10)
        assert db.get(GUILD, "level_no_xp_channels") is None
        assert next(f for f in out["fields"] if f["key"] == "level_no_xp_roles")["value"] == [str(GUILD + 10)]
        await call(client, "PUT", "/control/sections/level", {"values": {"level_no_xp_roles": ["123"]}}, status=400)
    run(test)


def test_aion_token_action():
    async def test(client, db, guild):
        out = await call(client, "POST", "/control/sections/aion/actions/token")
        token = db.get(GUILD, "aion_api_token")
        assert token and any(i["value"] == token for i in out["info"])
        await call(client, "POST", "/control/sections/aion/actions/gibtsnicht", status=404)
    run(test)


def test_level_rewards():
    async def test(client, db, guild):
        rows = await call(client, "PUT", "/control/level-rewards/5", {"role_id": str(GUILD + 10)})
        assert rows == [{"level": 5, "role_id": str(GUILD + 10), "role": "Mitglied"}]
        # Über der eigenen Rolle bzw. Integrationsrolle kann der Bot nicht vergeben
        await call(client, "PUT", "/control/level-rewards/6", {"role_id": str(GUILD + 12)}, status=400)
        await call(client, "PUT", "/control/level-rewards/6", {"role_id": str(GUILD + 11)}, status=400)
        await call(client, "PUT", "/control/level-rewards/0", {"role_id": str(GUILD + 10)}, status=400)
        await call(client, "DELETE", "/control/level-rewards/5", status=204)
        assert await call(client, "GET", "/control/level-rewards") == []
    run(test)


def test_announcements_and_commands():
    async def test(client, db, guild):
        rows = await call(client, "POST", "/control/announcements",
                          {"channel_id": str(GUILD + 21), "text": "Hallo", "interval_minutes": 60})
        assert rows[0]["channel"] == "chat" and rows[0]["interval_minutes"] == 60
        await call(client, "POST", "/control/announcements",
                   {"channel_id": str(GUILD + 21), "text": "x", "interval_minutes": 4}, status=400)
        await call(client, "DELETE", f"/control/announcements/{rows[0]['id']}", status=204)
        assert await call(client, "GET", "/control/announcements") == []

        rows = await call(client, "PUT", "/control/commands/Regeln", {"response": "Lies #regeln"})
        assert rows == [{"name": "regeln", "response": "Lies #regeln"}]
        await call(client, "PUT", "/control/commands/mit%20leerzeichen", {"response": "x"}, status=400)
        await call(client, "DELETE", "/control/commands/regeln", status=204)
        assert await call(client, "GET", "/control/commands") == []
    run(test)


def test_notifications_toggle_only_own_guild():
    async def test(client, db, guild):
        await db.execute("INSERT INTO feeds (guild_id, channel_id, kind, source, events) VALUES (?, ?, ?, ?, ?)",
                         (GUILD, GUILD + 21, "github", "owner/repo", json.dumps(["release"])))
        await db.execute("INSERT INTO feeds (guild_id, channel_id, kind, source) VALUES (?, ?, ?, ?)",
                         (123, 1, "github", "fremd/repo"))
        rows = await call(client, "GET", "/control/notifications")
        assert [(r["kind"], r["source"], r["channel"], r["enabled"]) for r in rows] == \
            [("GitHub", "owner/repo", "chat", True)]
        rows = await call(client, "POST", f"/control/notifications/{rows[0]['id']}/toggle")
        assert rows[0]["enabled"] is False
        await call(client, "POST", "/control/notifications/2/toggle", status=404)  # anderer Server
        await call(client, "DELETE", "/control/notifications/1", status=204)
        assert await call(client, "GET", "/control/notifications") == []
    run(test)


def test_matrix_toggle_with_reason():
    async def test(client, db, guild):
        data = await call(client, "GET", "/control/matrix")
        assert [r["name"] for r in data["roles"]] == ["Admin", "Mitglied"]
        assert [(r["name"], r["category"]) for r in data["rows"]] == \
            [("Allgemein", True), ("chat", False), ("Lobby", False)]
        assert data["rows"][1]["cells"] == [True, True]  # @everyone sieht alles

        resp = await client.put("/control/matrix", json={"channel_id": str(GUILD + 21), "role_id": str(GUILD + 10),
                                                         "allow": False},
                                headers={**AUTH, "X-Hub-User": "N%C3%A4vonex"})
        assert resp.status == 200
        assert (await resp.json())["rows"][1]["cells"] == [True, False]
        assert guild.get_channel(GUILD + 21).last_reason == "NexHub: Nävonex"
        await call(client, "PUT", "/control/matrix",
                   {"channel_id": str(GUILD + 21), "role_id": str(GUILD), "allow": True}, status=400)
    run(test)
