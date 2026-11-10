"""Steuer-API für den NexHub: dieselben Einstellungen wie im Web-Dashboard, aber als JSON.

Läuft als eigener aiohttp-Server im Bot (Port 8790, s. CONTROL_PORT) und startet nur, wenn
`BOT_CONTROL_KEY` gesetzt ist. Jede Anfrage braucht `Authorization: Bearer <BOT_CONTROL_KEY>`.
Gedacht für das interne Docker-Netz auf dem VPS: Der Port wird nie veröffentlicht, nur die
Hub-API (`/api/admin/bot/…`, nur Admins) spricht mit ihm. Wer angemeldet ist und ob er Admin ist,
prüft der Hub; der Bot vertraut dem Schlüssel und schreibt den Namen aus `X-Hub-User` ins
Discord-Audit-Log, wo er etwas am Server ändert.

Menü und Seiten des Hubs kommen aus `/control/pages`: Formular-Bereiche aus `SECTIONS`, dazu was
jeder Cog per `hub_pages()` beschreibt (Tabellen, Status, Aktionen, siehe `bot/hubpages.py`). Der
Hub zeichnet das allgemein, ohne die einzelnen Funktionen zu kennen. Eigene Endpunkte haben nur
noch die Seiten mit eigener Oberfläche (Level-Belohnungen, Ankündigungen, eigene Befehle,
Sichtbarkeits-Matrix, Regel-Text).

Discord-IDs gehen als Strings raus und rein: JavaScript rechnet mit Gleitkommazahlen und würde
die letzten Stellen einer 18-stelligen ID verfälschen.
"""

from __future__ import annotations

import hmac
import json
import logging
import os
import re
import time
import urllib.parse
from typing import Any, Awaitable, Callable

import discord
from aiohttp import web
from discord.ext import commands

from .. import hubpages
from ..errors import UserError
from ..forms import SECTIONS, Section, convert_field, parse_id, read_field, save_values
from ..hubpages import ApiError, Ctx, Field, Form, Page

log = logging.getLogger(__name__)

DEFAULT_PORT = 8790
STARTED = time.time()

TEXT_TYPES = hubpages.TEXT_TYPES
VOICE_TYPES = hubpages.VOICE_TYPES


# ---- Formular-Bereiche ---------------------------------------------------------------------

# Seiten, die nicht von einem Cog kommen: Formular-Bereiche oben und eigene Seiten im Hub
# (routes/hub/admin/bot/<id>). Alles andere liefern die Cogs per hub_pages() (siehe hubpages.py).
CORE_PAGES: tuple[Page, ...] = (
    Page("", "Übersicht", "Server", order=0, custom=True),
    Page("allgemein", "Allgemein", "Server", (Form("allgemein"),), SECTIONS["allgemein"].description, order=10),
    Page("verifizierung", "Verifizierung", "Server", order=20, custom=True),
    Page("tickets", "Tickets", "Server", (Form("tickets"),), SECTIONS["tickets"].description, order=30),
    Page("sichtbarkeit", "Sichtbarkeit", "Server", order=40, custom=True),
    Page("community", "Community", "Community", (Form("community"),), SECTIONS["community"].description, order=10),
    Page("level", "Levelsystem", "Community", order=20, custom=True),
    Page("ankuendigungen", "Ankündigungen", "Community", order=60, custom=True),
    Page("befehle", "Eigene Befehle", "Community", order=70, custom=True),
    Page("verwarnungen", "Automatische Strafe", "Moderation", (Form("verwarnungen"),),
         SECTIONS["verwarnungen"].description, order=30),
    Page("automod", "Automod", "Moderation", (Form("automod"),), SECTIONS["automod"].description, order=40),
    Page("aion", "AION 2", "Spiele", (Form("aion"),), SECTIONS["aion"].description, order=10),
)


# ---- Server-Daten für Auswahllisten ----------------------------------------------------------

def channel_kind(ch) -> str | None:
    if ch.type in TEXT_TYPES:
        return "text"
    if ch.type in VOICE_TYPES:
        return "voice"
    if ch.type == discord.ChannelType.category:
        return "category"
    return None


def channel_order(ch) -> tuple:
    """Reihenfolge wie in der Discord-Seitenleiste: Kategorie für Kategorie, darin erst Text,
    dann Sprache. `position` allein zählt nur innerhalb einer Kategorie und Kanalart."""
    if ch.type == discord.ChannelType.category:
        return (ch.position, 0, 0, 0, ch.id)
    cat = getattr(ch, "category", None)
    return (cat.position if cat else -1, 1, ch.type in VOICE_TYPES, ch.position, ch.id)


def guild_info(guild) -> dict:
    """Kanäle und Rollen in Discord-Reihenfolge, für Auswahllisten im Hub."""
    channels = []
    for ch in sorted(guild.channels, key=channel_order):
        kind = channel_kind(ch)
        if kind:
            channels.append({"id": str(ch.id), "name": ch.name, "kind": kind,
                             "category": str(ch.category.id) if getattr(ch, "category", None) else None})
    me_top = guild.me.top_role if guild.me else None
    roles = [{"id": str(r.id), "name": r.name, "color": str(r.color) if r.color.value else None,
              # Rollen über der eigenen kann der Bot nicht vergeben (z. B. als Level-Belohnung)
              "assignable": me_top is None or r < me_top}
             for r in sorted(guild.roles, key=lambda r: -r.position) if not r.is_default() and not r.managed]
    people = sorted((m for m in guild.members if not m.bot), key=lambda m: m.display_name.lower())[:2000]
    return {"id": str(guild.id), "name": guild.name,
            "icon_url": str(guild.icon.url) if guild.icon else None,
            "members": guild.member_count or len(guild.members), "channels": channels, "roles": roles,
            "people": [{"id": str(m.id), "name": m.display_name, "tag": m.name} for m in people]}


def visible_roles(guild: discord.Guild) -> list[discord.Role]:
    """Echte Mitglieder-Rollen für die Sichtbarkeits-Matrix — ohne @everyone und ohne
    bot-eigene Integrations-Rollen (TheWashbot, Jellyfin, …), die kann man eh nicht manuell vergeben."""
    return sorted((r for r in guild.roles if not r.is_default() and not r.managed), key=lambda r: -r.position)


def role_can_view(channel, role: discord.Role, everyone: discord.Role) -> bool:
    """Könnte ein Mitglied, das nur @everyone + diese eine Rolle hat, den Kanal/die Kategorie
    sehen? (Admin-Rechte/Owner-Status bleiben hier bewusst außen vor — reine Rollen-Perspektive.)"""
    base = everyone.permissions.value | role.permissions.value
    VIEW = 1 << 10
    for target in (everyone, role):
        ow = channel.overwrites_for(target)
        if ow.view_channel is False:
            base &= ~VIEW
        elif ow.view_channel is True:
            base |= VIEW
    return bool(base & VIEW)


def matrix(guild) -> dict:
    """Wer sieht welchen Kanal: Zeilen = Kategorien mit ihren Kanälen, Spalten = Rollen."""
    everyone = guild.default_role
    roles = visible_roles(guild)

    def row(ch, category: bool) -> dict:
        return {"id": str(ch.id), "name": ch.name, "category": category,
                "kind": channel_kind(ch), "cells": [role_can_view(ch, r, everyone) for r in roles]}

    rows = []
    for cat in sorted(guild.categories, key=lambda c: c.position):
        rows.append(row(cat, True))
        rows.extend(row(c, False) for c in sorted(cat.channels, key=lambda c: c.position)
                    if c.type in TEXT_TYPES + VOICE_TYPES)
    loose = sorted((c for c in guild.channels if c.category is None and c.type in TEXT_TYPES + VOICE_TYPES),
                   key=lambda c: c.position)
    if loose:
        rows.append({"id": None, "name": "(ohne Kategorie)", "category": True, "kind": None, "cells": []})
        rows.extend(row(c, False) for c in loose)
    return {"roles": [{"id": str(r.id), "name": r.name} for r in roles], "rows": rows}


# ---- Server ------------------------------------------------------------------------------------

Handler = Callable[[web.Request], Awaitable[Any]]


class Control(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.db = bot.db
        self.runner: web.AppRunner | None = None
        self.key = os.getenv("BOT_CONTROL_KEY", "").strip()

    def make_app(self) -> web.Application:
        app = web.Application(middlewares=[self._middleware], client_max_size=256 * 1024)
        r = app.router
        r.add_get("/control/status", self.status)
        r.add_get("/control/guild", self.guild_data)
        r.add_get("/control/sections", self.sections)
        r.add_put("/control/sections/{id}", self.save_section)
        r.add_post("/control/sections/{id}/actions/{action}", self.section_action)
        r.add_get("/control/verification", self.verification)
        r.add_put("/control/verification/text", self.verification_text)
        r.add_get("/control/level-rewards", self.rewards)
        r.add_put("/control/level-rewards/{level}", self.reward_set)
        r.add_delete("/control/level-rewards/{level}", self.reward_delete)
        r.add_get("/control/announcements", self.announcements)
        r.add_post("/control/announcements", self.announcement_add)
        r.add_delete("/control/announcements/{id}", self.announcement_delete)
        r.add_get("/control/commands", self.custom_commands)
        r.add_put("/control/commands/{name}", self.command_set)
        r.add_delete("/control/commands/{name}", self.command_delete)
        r.add_get("/control/matrix", self.matrix)
        r.add_put("/control/matrix", self.matrix_set)
        r.add_post("/control/run-link", self.run_link)
        r.add_get("/control/pages", self.pages)
        r.add_get("/control/pages/{page}", self.page)
        r.add_post("/control/pages/{page}/{block}/{action}", self.page_action)
        return app

    async def cog_load(self) -> None:
        if not self.key:
            log.info("BOT_CONTROL_KEY fehlt – Steuer-API für den NexHub ist aus")
            return
        if len(self.key) < 24:
            log.warning("BOT_CONTROL_KEY ist zu kurz (mindestens 24 Zeichen) – Steuer-API bleibt aus")
            return
        self.runner = web.AppRunner(self.make_app())
        await self.runner.setup()
        port = int(os.getenv("CONTROL_PORT", DEFAULT_PORT))
        await web.TCPSite(self.runner, os.getenv("CONTROL_HOST", "0.0.0.0"), port).start()
        log.info("Steuer-API hört auf Port %d", port)

    async def cog_unload(self) -> None:
        if self.runner:
            await self.runner.cleanup()

    @web.middleware
    async def _middleware(self, request: web.Request, handler: Handler) -> web.StreamResponse:
        scheme, _, token = request.headers.get("Authorization", "").partition(" ")
        if scheme.lower() != "bearer" or not hmac.compare_digest(token.encode(), self.key.encode()):
            return web.json_response({"detail": "Schlüssel fehlt oder falsch"}, status=401)
        try:
            result = await handler(request)
        except ApiError as e:
            return web.json_response({"detail": e.detail}, status=e.status)
        except UserError as e:
            return web.json_response({"detail": str(e)}, status=400)
        except web.HTTPException as e:
            return web.json_response({"detail": e.reason}, status=e.status)
        except discord.Forbidden:
            return web.json_response({"detail": "Dafür fehlen dem Bot die Rechte auf dem Server"}, status=409)
        except discord.HTTPException as e:
            return web.json_response({"detail": f"Discord: {e.text or e.status}"}, status=502)
        except Exception:
            log.exception("Steuer-API: Fehler bei %s %s", request.method, request.path)
            return web.json_response({"detail": "Fehler im Bot, Details stehen im Log"}, status=500)
        if isinstance(result, web.StreamResponse):
            return result
        if result is None:
            return web.Response(status=204)
        return web.json_response(result)

    # ---- Hilfsfunktionen -----------------------------------------------------------------------

    def guild(self) -> discord.Guild:
        gid = os.getenv("DEV_GUILD_ID", "").strip()
        guild = self.bot.get_guild(int(gid)) if gid.isdigit() else (self.bot.guilds[0] if self.bot.guilds else None)
        if guild is None:
            raise ApiError(503, "Bot ist mit keinem Discord-Server verbunden")
        return guild

    @staticmethod
    async def body(request: web.Request) -> dict:
        try:
            data = await request.json()
        except (json.JSONDecodeError, UnicodeDecodeError):
            raise ApiError(400, "JSON erwartet") from None
        if not isinstance(data, dict):
            raise ApiError(400, "JSON-Objekt erwartet")
        return data

    @staticmethod
    def reason(request: web.Request) -> str:
        # Der Hub schickt den Namen URL-kodiert, weil Header nur Latin-1 können
        who = urllib.parse.unquote(request.headers.get("X-Hub-User", "")).strip()[:60]
        return f"NexHub: {who}" if who else "NexHub"

    # ---- Status und Server ---------------------------------------------------------------------

    async def status(self, request: web.Request) -> dict:
        user = self.bot.user
        gid = os.getenv("DEV_GUILD_ID", "").strip()
        guild = self.bot.get_guild(int(gid)) if gid.isdigit() else (self.bot.guilds[0] if self.bot.guilds else None)
        latency = self.bot.latency
        return {
            "ready": self.bot.is_ready(),
            "name": str(user) if user else None,
            "avatar_url": str(user.display_avatar.url) if user else None,
            "guild": {"id": str(guild.id), "name": guild.name, "members": guild.member_count or len(guild.members),
                      "icon_url": str(guild.icon.url) if guild.icon else None} if guild else None,
            "guilds": len(self.bot.guilds),
            "latency_ms": round(latency * 1000) if latency == latency and latency != float("inf") else None,
            "uptime_s": round(time.time() - STARTED),
            "version": os.getenv("GIT_REV", "dev"),
            "cogs": sorted(self.bot.cogs),
        }

    async def guild_data(self, request: web.Request) -> dict:
        return guild_info(self.guild())

    # ---- Formular-Bereiche ---------------------------------------------------------------------

    def runs(self) -> Any:
        """Das Modul aion2.runs, wenn der Bot Module hat (in Tests der Steuer-API fehlen sie)."""
        if not hasattr(self.bot, "modules"):
            return None
        return self.bot.modules.module("aion2.runs")

    def section_info(self, guild, s: Section) -> list[dict]:
        """Nur-Lese-Angaben unter einem Formular, z. B. Adresse und Token für das NexBoard."""
        if s.id == "aion":
            aion = self.runs()
            return [
                {"label": "Endpunkt", "value": aion.api_url() if aion else None, "code": True},
                {"label": "Token", "value": self.db.get(guild.id, "aion_api_token"), "code": True, "secret": True},
            ]
        return []

    def section_out(self, guild, s: Section) -> dict:
        return {
            "id": s.id, "title": s.title, "description": s.description, "note": s.note,
            "fields": [f.out(read_field(self.db, guild.id, f)) for f in s.fields],
            "info": self.section_info(guild, s),
            "actions": [{"id": k, "label": v} for k, v in s.actions.items()],
        }

    def _section(self, request: web.Request) -> Section:
        s = SECTIONS.get(request.match_info["id"])
        if s is None:
            raise ApiError(404, "Bereich gibt es nicht")
        return s

    async def sections(self, request: web.Request) -> list[dict]:
        guild = self.guild()
        return [self.section_out(guild, s) for s in SECTIONS.values()]

    async def save_section(self, request: web.Request) -> dict:
        """Speichert die mitgeschickten Felder eines Bereichs (fehlende bleiben, wie sie sind)."""
        guild = self.guild()
        s = self._section(request)
        values = (await self.body(request)).get("values")
        if not isinstance(values, dict):
            raise ApiError(400, "values fehlt")
        await save_values(self.bot, self.db, guild, s, values)
        return self.section_out(guild, s)

    async def section_action(self, request: web.Request) -> dict:
        guild = self.guild()
        s = self._section(request)
        action = request.match_info["action"]
        if action not in s.actions:
            raise ApiError(404, "Aktion gibt es nicht")
        if (s.id, action) == ("aion", "token"):
            aion = self.runs()
            if aion is not None:
                await aion.token(guild.id, renew=True)
        return self.section_out(guild, s)

    # ---- Verifizierung -------------------------------------------------------------------------

    def verify_module(self) -> Any:
        """Das Modul server.verification (in Tests der Steuer-API fehlen die Module)."""
        if not hasattr(self.bot, "modules"):
            raise ApiError(503, "Verifizierung ist nicht geladen")
        return self.bot.modules.module("server.verification")

    async def verification(self, request: web.Request) -> dict:
        guild = self.guild()
        module = self.verify_module()
        settings = module.settings.get(guild.id)
        channel = module.rules_channel(guild)
        role = guild.get_role(settings.verify_role or 0)
        message = await module.rules_message(guild)
        text = message.embeds[0].description if message and message.embeds else None
        return {"channel": channel.name if channel else None, "role": role.name if role else None,
                "panel": message is not None, "text": text}

    async def verification_text(self, request: web.Request) -> None:
        text = str((await self.body(request)).get("text") or "")
        await self.verify_module().set_text(self.guild(), text)

    # ---- Level-Belohnungen ---------------------------------------------------------------------

    async def rewards(self, request: web.Request) -> list[dict]:
        guild = self.guild()
        rows = await self.db.fetchall(
            "SELECT level, role_id FROM level_rewards WHERE guild_id=? ORDER BY level", (guild.id,))
        out = []
        for r in rows:
            role = guild.get_role(r["role_id"])
            out.append({"level": r["level"], "role_id": str(r["role_id"]), "role": role.name if role else None})
        return out

    @staticmethod
    def _level(request: web.Request) -> int:
        level = request.match_info["level"]
        if not level.isdigit() or not 1 <= int(level) <= 1000:
            raise ApiError(400, "Level zwischen 1 und 1000")
        return int(level)

    async def reward_set(self, request: web.Request) -> list[dict]:
        guild = self.guild()
        level = self._level(request)
        role_id = parse_id((await self.body(request)).get("role_id"), "Rolle")
        role = guild.get_role(role_id or 0)
        if role is None:
            raise ApiError(400, "Rolle gibt es nicht")
        if role.managed or (guild.me and role >= guild.me.top_role):
            raise ApiError(400, f"{role.name} kann der Bot nicht vergeben (muss unter seiner eigenen Rolle stehen)")
        await self.db.execute(
            "INSERT INTO level_rewards (guild_id, level, role_id) VALUES (?, ?, ?) "
            "ON CONFLICT(guild_id, level) DO UPDATE SET role_id=excluded.role_id",
            (guild.id, level, role.id))
        return await self.rewards(request)

    async def reward_delete(self, request: web.Request) -> None:
        guild = self.guild()
        await self.db.execute("DELETE FROM level_rewards WHERE guild_id=? AND level=?",
                              (guild.id, self._level(request)))

    # ---- Ankündigungen -------------------------------------------------------------------------

    async def announcements(self, request: web.Request) -> list[dict]:
        guild = self.guild()
        rows = await self.db.fetchall(
            "SELECT id, channel_id, text, interval_minutes, next_run FROM scheduled WHERE guild_id=? ORDER BY id",
            (guild.id,))
        out = []
        for r in rows:
            ch = guild.get_channel(r["channel_id"])
            out.append({"id": r["id"], "channel_id": str(r["channel_id"]), "channel": ch.name if ch else None,
                        "text": r["text"], "interval_minutes": r["interval_minutes"], "next_run": r["next_run"]})
        return out

    async def announcement_add(self, request: web.Request) -> list[dict]:
        guild = self.guild()
        data = await self.body(request)
        channel_id = convert_field(guild, Field("channel", "channel", "Kanal"), data.get("channel_id"))
        text = str(data.get("text") or "").strip()
        interval = data.get("interval_minutes")
        if channel_id is None or not text:
            raise ApiError(400, "Kanal und Text angeben")
        if len(text) > 2000:
            raise ApiError(400, "Höchstens 2000 Zeichen (Discord-Grenze)")
        if isinstance(interval, bool) or not isinstance(interval, int) or interval < 5:
            raise ApiError(400, "Intervall mindestens 5 Minuten")
        await self.db.execute(
            "INSERT INTO scheduled (guild_id, channel_id, text, interval_minutes, next_run) VALUES (?, ?, ?, ?, ?)",
            (guild.id, channel_id, text, interval, time.time()))
        return await self.announcements(request)

    async def announcement_delete(self, request: web.Request) -> None:
        guild = self.guild()
        ann_id = request.match_info["id"]
        if not ann_id.isdigit():
            raise ApiError(404, "Ankündigung gibt es nicht")
        await self.db.execute("DELETE FROM scheduled WHERE id=? AND guild_id=?", (int(ann_id), guild.id))

    # ---- Eigene Befehle ------------------------------------------------------------------------

    async def custom_commands(self, request: web.Request) -> list[dict]:
        guild = self.guild()
        rows = await self.db.fetchall(
            "SELECT name, response FROM custom_commands WHERE guild_id=? ORDER BY name", (guild.id,))
        return [{"name": r["name"], "response": r["response"]} for r in rows]

    @staticmethod
    def _command_name(request: web.Request) -> str:
        name = request.match_info["name"].strip().lower().lstrip("!")
        if not re.fullmatch(r"[a-z0-9_-]{1,32}", name):
            raise ApiError(400, "Name: 1–32 Zeichen, nur a–z, 0–9, _ und -")
        return name

    async def command_set(self, request: web.Request) -> list[dict]:
        guild = self.guild()
        name = self._command_name(request)
        response = str((await self.body(request)).get("response") or "").strip()
        if not response:
            raise ApiError(400, "Antwort fehlt")
        if len(response) > 2000:
            raise ApiError(400, "Höchstens 2000 Zeichen (Discord-Grenze)")
        await self.db.execute(
            "INSERT INTO custom_commands (guild_id, name, response) VALUES (?, ?, ?) "
            "ON CONFLICT(guild_id, name) DO UPDATE SET response=excluded.response",
            (guild.id, name, response))
        return await self.custom_commands(request)

    async def command_delete(self, request: web.Request) -> None:
        guild = self.guild()
        await self.db.execute("DELETE FROM custom_commands WHERE guild_id=? AND name=?",
                              (guild.id, self._command_name(request)))

    # ---- Sichtbarkeits-Matrix ------------------------------------------------------------------

    async def matrix(self, request: web.Request) -> dict:
        return matrix(self.guild())

    async def matrix_set(self, request: web.Request) -> dict:
        """Eine Zelle umschalten: diese Rolle darf den Kanal sehen (`allow`) oder nicht."""
        guild = self.guild()
        data = await self.body(request)
        channel = guild.get_channel(parse_id(data.get("channel_id"), "Kanal") or 0)
        role = guild.get_role(parse_id(data.get("role_id"), "Rolle") or 0)
        if channel is None or role is None or role.is_default() or role.managed:
            raise ApiError(400, "Kanal oder Rolle gibt es nicht")
        if not isinstance(data.get("allow"), bool):
            raise ApiError(400, "allow: ja/nein erwartet")
        await channel.set_permissions(role, view_channel=data["allow"], reason=self.reason(request))
        return matrix(guild)

    # ---- Seiten (hubpages.py) ------------------------------------------------------------------

    def all_pages(self) -> list[Page]:
        pages = list(CORE_PAGES)
        if hasattr(self.bot, "modules"):  # neue Module (bot/modules) neben den alten Cogs
            pages.extend(self.bot.modules.pages())
        for cog in self.bot.cogs.values():
            if hasattr(cog, "hub_pages"):
                pages.extend(cog.hub_pages())
        return sorted(pages, key=lambda p: (hubpages.group_rank(p.group), p.order, p.title))

    def _page(self, request: web.Request) -> Page:
        pid = request.match_info["page"]
        for p in self.all_pages():
            if p.id == pid and not p.custom:
                return p
        raise ApiError(404, "Diese Seite hat der Bot nicht")

    def ctx(self, request: web.Request) -> Ctx:
        who = urllib.parse.unquote(request.headers.get("X-Hub-User", "")).strip()[:60]
        uid = request.headers.get("X-Hub-User-Id", "")
        return Ctx(self.bot, self.guild(), who, int(uid) if uid.isdigit() else None)

    async def pages(self, request: web.Request) -> list[dict]:
        self.guild()
        return [p.nav() for p in self.all_pages()]

    async def page(self, request: web.Request) -> dict:
        ctx = self.ctx(request)
        return await hubpages.page_out(ctx, self._page(request),
                                       lambda sid: self.section_out(ctx.guild, SECTIONS[sid]))

    async def page_action(self, request: web.Request) -> dict:
        """Aktion ausführen, danach die Seite neu liefern (Tabellen und Status sind dann aktuell)."""
        ctx = self.ctx(request)
        page = self._page(request)
        action = page.action(request.match_info["block"], request.match_info["action"])
        data = await self.body(request)
        values = hubpages.action_values(ctx.guild, action.fields, data.get("values"))
        item = data.get("item")
        try:
            message = await action.run(ctx, values, str(item) if item is not None else None)
        except UserError as e:
            raise ApiError(400, str(e)) from None
        log.info("Hub-Aktion %s/%s/%s von %s", page.id, request.match_info["block"], action.id, ctx.who or "?")
        out = await hubpages.page_out(ctx, page, lambda sid: self.section_out(ctx.guild, SECTIONS[sid]))
        return {"message": message or "Erledigt.", "page": out}

    # ---- Runs aus dem Hub ---------------------------------------------------------------------

    async def run_link(self, request: web.Request) -> dict:
        """Der Hub hat einen Run gespeichert: Link an den passenden AION-Post (aion2.runs, attach_hub_link)."""
        data = await self.body(request)
        dungeon, start_ms, url = data.get("dungeon"), data.get("start_ms"), data.get("url")
        if not isinstance(dungeon, str) or not dungeon.strip():
            raise ApiError(400, "dungeon fehlt")
        if not isinstance(start_ms, int) or isinstance(start_ms, bool):
            raise ApiError(400, "start_ms fehlt")
        if not isinstance(url, str) or not url.startswith(("https://", "http://")) or len(url) > 500:
            raise ApiError(400, "url fehlt oder ungültig")
        aion = self.runs()
        if aion is None:
            raise ApiError(503, "AION-Modul ist nicht geladen")
        return {"result": await aion.attach_hub_link(dungeon.strip(), start_ms, url)}


async def setup(bot) -> None:
    await bot.add_cog(Control(bot))
