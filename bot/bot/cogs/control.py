"""Steuer-API für den NexHub: dieselben Einstellungen wie im Web-Dashboard, aber als JSON.

Läuft als eigener aiohttp-Server im Bot (Port 8790, s. CONTROL_PORT) und startet nur, wenn
`BOT_CONTROL_KEY` gesetzt ist. Jede Anfrage braucht `Authorization: Bearer <BOT_CONTROL_KEY>`.
Gedacht für das interne Docker-Netz auf dem VPS: Der Port wird nie veröffentlicht, nur die
Hub-API (`/api/admin/bot/…`, nur Admins) spricht mit ihm. Wer angemeldet ist und ob er Admin ist,
prüft der Hub; der Bot vertraut dem Schlüssel und schreibt den Namen aus `X-Hub-User` ins
Discord-Audit-Log, wo er etwas am Server ändert.

Menü und Seiten des Hubs kommen aus `/control/pages`: Formular-Bereiche aus `SECTIONS`, dazu was
jedes Modul per `pages()` beschreibt (Tabellen, Status, Aktionen, siehe `bot/hubpages.py`). Der
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
import time
import urllib.parse
from collections.abc import Awaitable, Callable
from typing import TYPE_CHECKING, Any

import discord
from aiohttp import web
from discord.ext import commands

from .. import hubpages
from ..core.discord_checks import can_assign
from ..errors import UserError
from ..forms import SECTIONS, Section, convert_field, parse_id, read_field, save_values
from ..hubpages import ApiError, Ctx, Field, Form, Page
from ..modules.aion2.runs import RunPosts
from ..modules.community.levels import Levels
from ..modules.community.levels.store import LevelStore
from ..modules.server.announcements import Announcements, AnnouncementStore
from ..modules.server.custom_commands import CommandStore, CustomCommands
from ..modules.server.verification import Verification

if TYPE_CHECKING:
    from ..__main__ import Bot

log = logging.getLogger(__name__)

DEFAULT_PORT = 8790
MAX_MESSAGE = 2000  # Länge einer Discord-Nachricht
MIN_INTERVAL_MIN = 5
MAX_BODY_BYTES = 256 * 1024
STARTED = time.time()

TEXT_TYPES = hubpages.TEXT_TYPES
VOICE_TYPES = hubpages.VOICE_TYPES


# ---- Formular-Bereiche ---------------------------------------------------------------------

# Seiten, die nicht von einem Cog kommen: Formular-Bereiche oben und eigene Seiten im Hub
# (routes/hub/admin/bot/<id>). Alles andere liefern die Module per pages() (siehe hubpages.py).
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

def channel_kind(ch: discord.abc.GuildChannel) -> str | None:
    if ch.type in TEXT_TYPES:
        return "text"
    if ch.type in VOICE_TYPES:
        return "voice"
    if ch.type == discord.ChannelType.category:
        return "category"
    return None


def channel_order(ch: discord.abc.GuildChannel) -> tuple[Any, ...]:
    """Reihenfolge wie in der Discord-Seitenleiste: Kategorie für Kategorie, darin erst Text,
    dann Sprache. `position` allein zählt nur innerhalb einer Kategorie und Kanalart."""
    if ch.type == discord.ChannelType.category:
        return (ch.position, 0, 0, 0, ch.id)
    cat = getattr(ch, "category", None)
    return (cat.position if cat else -1, 1, ch.type in VOICE_TYPES, ch.position, ch.id)


def guild_info(guild: discord.Guild) -> dict[str, Any]:
    """Kanäle und Rollen in Discord-Reihenfolge, für Auswahllisten im Hub."""
    channels = []
    for ch in sorted(guild.channels, key=channel_order):
        kind = channel_kind(ch)
        if kind:
            category = getattr(ch, "category", None)
            channels.append({"id": str(ch.id), "name": ch.name, "kind": kind,
                             "category": str(category.id) if category else None})
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


def role_can_view(channel: discord.abc.GuildChannel, role: discord.Role, everyone: discord.Role) -> bool:
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


def matrix(guild: discord.Guild) -> dict[str, Any]:
    """Wer sieht welchen Kanal: Zeilen = Kategorien mit ihren Kanälen, Spalten = Rollen."""
    everyone = guild.default_role
    roles = visible_roles(guild)

    def row(ch: discord.abc.GuildChannel, category: bool) -> dict[str, Any]:
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

Handler = Callable[[web.Request], Awaitable[web.StreamResponse]]
JsonHandler = Callable[[web.Request], Awaitable[Any]]  # gibt JSON-Daten zurück, None heißt 204


def as_json(handler: JsonHandler) -> Handler:
    """Macht aus dem Rückgabewert eines Handlers die HTTP-Antwort."""

    async def respond(request: web.Request) -> web.StreamResponse:
        result = await handler(request)
        if result is None:
            return web.Response(status=204)
        return web.json_response(result)

    return respond


class Control(commands.Cog):
    def __init__(self, bot: Bot) -> None:
        self.bot = bot
        self.db = bot.db
        self.runner: web.AppRunner | None = None
        self.key = os.getenv("BOT_CONTROL_KEY", "").strip()

    def make_app(self) -> web.Application:
        app = web.Application(middlewares=[self._middleware], client_max_size=MAX_BODY_BYTES)
        routes: list[tuple[str, str, JsonHandler]] = [
            ("GET", "/control/status", self.status),
            ("GET", "/control/guild", self.guild_data),
            ("GET", "/control/sections", self.sections),
            ("PUT", "/control/sections/{id}", self.save_section),
            ("POST", "/control/sections/{id}/actions/{action}", self.section_action),
            ("GET", "/control/verification", self.verification),
            ("PUT", "/control/verification/text", self.verification_text),
            ("GET", "/control/level-rewards", self.rewards),
            ("PUT", "/control/level-rewards/{level}", self.reward_set),
            ("DELETE", "/control/level-rewards/{level}", self.reward_delete),
            ("GET", "/control/announcements", self.announcements),
            ("POST", "/control/announcements", self.announcement_add),
            ("DELETE", "/control/announcements/{id}", self.announcement_delete),
            ("GET", "/control/commands", self.custom_commands),
            ("PUT", "/control/commands/{name}", self.command_set),
            ("DELETE", "/control/commands/{name}", self.command_delete),
            ("GET", "/control/matrix", self.matrix),
            ("PUT", "/control/matrix", self.matrix_set),
            ("POST", "/control/run-link", self.run_link),
            ("GET", "/control/pages", self.pages),
            ("GET", "/control/pages/{page}", self.page),
            ("POST", "/control/pages/{page}/{block}/{action}", self.page_action),
        ]
        for method, path, handler in routes:
            app.router.add_route(method, path, as_json(handler))
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
            return await handler(request)
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

    # ---- Hilfsfunktionen -----------------------------------------------------------------------

    def find_guild(self) -> discord.Guild | None:
        """Der Server aus DEV_GUILD_ID, sonst der erste, auf dem der Bot ist."""
        gid = os.getenv("DEV_GUILD_ID", "").strip()
        if gid.isdigit():
            return self.bot.get_guild(int(gid))
        return self.bot.guilds[0] if self.bot.guilds else None

    def guild(self) -> discord.Guild:
        guild = self.find_guild()
        if guild is None:
            raise ApiError(503, "Bot ist mit keinem Discord-Server verbunden")
        return guild

    @staticmethod
    async def body(request: web.Request) -> dict[str, Any]:
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

    async def status(self, request: web.Request) -> dict[str, Any]:
        user = self.bot.user
        guild = self.find_guild()
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

    async def guild_data(self, request: web.Request) -> dict[str, Any]:
        return guild_info(self.guild())

    # ---- Formular-Bereiche ---------------------------------------------------------------------

    def runs(self) -> RunPosts:
        return self.bot.modules.module("aion2.runs", RunPosts)

    def section_info(self, guild: discord.Guild, s: Section) -> list[dict[str, Any]]:
        """Nur-Lese-Angaben unter einem Formular, z. B. Adresse und Token für das NexBoard."""
        if s.id == "aion":
            return [
                {"label": "Endpunkt", "value": self.runs().api_url(), "code": True},
                {"label": "Token", "value": self.db.get(guild.id, "aion_api_token"), "code": True, "secret": True},
            ]
        return []

    def section_out(self, guild: discord.Guild, s: Section) -> dict[str, Any]:
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

    async def sections(self, request: web.Request) -> list[dict[str, Any]]:
        guild = self.guild()
        return [self.section_out(guild, s) for s in SECTIONS.values()]

    async def save_section(self, request: web.Request) -> dict[str, Any]:
        """Speichert die mitgeschickten Felder eines Bereichs (fehlende bleiben, wie sie sind)."""
        guild = self.guild()
        s = self._section(request)
        values = (await self.body(request)).get("values")
        if not isinstance(values, dict):
            raise ApiError(400, "values fehlt")
        await save_values(self.bot, self.db, guild, s, values)
        return self.section_out(guild, s)

    async def section_action(self, request: web.Request) -> dict[str, Any]:
        guild = self.guild()
        s = self._section(request)
        action = request.match_info["action"]
        if action not in s.actions:
            raise ApiError(404, "Aktion gibt es nicht")
        if (s.id, action) == ("aion", "token"):
            await self.runs().token(guild.id, renew=True)
        return self.section_out(guild, s)

    # ---- Verifizierung -------------------------------------------------------------------------

    def verify_module(self) -> Verification:
        return self.bot.modules.module("server.verification", Verification)

    async def verification(self, request: web.Request) -> dict[str, Any]:
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

    # ---- Daten der Module (Level-Belohnungen, Ankündigungen, eigene Befehle) --------------------

    # Dieselben Stores, die auch die Slash-Befehle der Module benutzen
    def levels(self) -> LevelStore:
        return self.bot.modules.module("community.levels", Levels).store

    def announcement_store(self) -> AnnouncementStore:
        return self.bot.modules.module("server.announcements", Announcements).store

    def command_store(self) -> CommandStore:
        return self.bot.modules.module("server.custom_commands", CustomCommands).store

    async def rewards(self, request: web.Request) -> list[dict[str, Any]]:
        guild = self.guild()
        out = []
        for r in await self.levels().rewards(guild.id):
            role = guild.get_role(r["role_id"])
            out.append({"level": r["level"], "role_id": str(r["role_id"]), "role": role.name if role else None})
        return out

    @staticmethod
    def _level(request: web.Request) -> int:
        level = request.match_info["level"]
        if not level.isdigit() or not 1 <= int(level) <= 1000:
            raise ApiError(400, "Level zwischen 1 und 1000")
        return int(level)

    async def reward_set(self, request: web.Request) -> list[dict[str, Any]]:
        guild = self.guild()
        level = self._level(request)
        role = guild.get_role(parse_id((await self.body(request)).get("role_id"), "Rolle") or 0)
        if role is None:
            raise ApiError(400, "Rolle gibt es nicht")
        if not can_assign(guild, role):
            raise ApiError(400, f"{role.name} kann der Bot nicht vergeben (muss unter seiner eigenen Rolle stehen)")
        await self.levels().set_reward(guild.id, level, role.id)
        return await self.rewards(request)

    async def reward_delete(self, request: web.Request) -> None:
        await self.levels().set_reward(self.guild().id, self._level(request), None)

    async def announcements(self, request: web.Request) -> list[dict[str, Any]]:
        guild = self.guild()
        out = []
        for r in await self.announcement_store().of_guild(guild.id):
            ch = guild.get_channel(r["channel_id"])
            out.append({"id": r["id"], "channel_id": str(r["channel_id"]), "channel": ch.name if ch else None,
                        "text": r["text"], "interval_minutes": r["interval_minutes"], "next_run": r["next_run"]})
        return out

    async def announcement_add(self, request: web.Request) -> list[dict[str, Any]]:
        guild = self.guild()
        data = await self.body(request)
        channel_id = convert_field(guild, Field("channel", "channel", "Kanal"), data.get("channel_id"))
        text = str(data.get("text") or "").strip()
        interval = data.get("interval_minutes")
        if channel_id is None or not text:
            raise ApiError(400, "Kanal und Text angeben")
        if len(text) > MAX_MESSAGE:
            raise ApiError(400, f"Höchstens {MAX_MESSAGE} Zeichen (Discord-Grenze)")
        if isinstance(interval, bool) or not isinstance(interval, int) or interval < MIN_INTERVAL_MIN:
            raise ApiError(400, f"Intervall mindestens {MIN_INTERVAL_MIN} Minuten")
        await self.announcement_store().add(guild.id, int(channel_id), text, interval)
        return await self.announcements(request)

    async def announcement_delete(self, request: web.Request) -> None:
        ann_id = request.match_info["id"]
        if not ann_id.isdigit():
            raise ApiError(404, "Ankündigung gibt es nicht")
        await self.announcement_store().delete(self.guild().id, int(ann_id))

    async def custom_commands(self, request: web.Request) -> list[dict[str, Any]]:
        rows = await self.command_store().of_guild(self.guild().id)
        return [{"name": r["name"], "response": r["response"]} for r in rows]

    async def command_set(self, request: web.Request) -> list[dict[str, Any]]:
        guild = self.guild()
        response = str((await self.body(request)).get("response") or "").strip()
        if not response:
            raise ApiError(400, "Antwort fehlt")
        if len(response) > MAX_MESSAGE:
            raise ApiError(400, f"Höchstens {MAX_MESSAGE} Zeichen (Discord-Grenze)")
        await self.command_store().put(guild.id, request.match_info["name"], response)
        return await self.custom_commands(request)

    async def command_delete(self, request: web.Request) -> None:
        await self.command_store().delete(self.guild().id, request.match_info["name"])

    # ---- Sichtbarkeits-Matrix ------------------------------------------------------------------

    async def matrix(self, request: web.Request) -> dict[str, Any]:
        return matrix(self.guild())

    async def matrix_set(self, request: web.Request) -> dict[str, Any]:
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
        pages = list(CORE_PAGES) + self.bot.modules.pages()
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

    async def pages(self, request: web.Request) -> list[dict[str, Any]]:
        self.guild()
        return [p.nav() for p in self.all_pages()]

    async def page(self, request: web.Request) -> dict[str, Any]:
        ctx = self.ctx(request)
        return await hubpages.page_out(ctx, self._page(request),
                                       lambda sid: self.section_out(ctx.guild, SECTIONS[sid]))

    async def page_action(self, request: web.Request) -> dict[str, Any]:
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

    async def run_link(self, request: web.Request) -> dict[str, Any]:
        """Der Hub hat einen Run gespeichert: Link an den passenden AION-Post (aion2.runs, attach_hub_link)."""
        data = await self.body(request)
        dungeon, start_ms, url = data.get("dungeon"), data.get("start_ms"), data.get("url")
        if not isinstance(dungeon, str) or not dungeon.strip():
            raise ApiError(400, "dungeon fehlt")
        if not isinstance(start_ms, int) or isinstance(start_ms, bool):
            raise ApiError(400, "start_ms fehlt")
        if not isinstance(url, str) or not url.startswith(("https://", "http://")) or len(url) > 500:
            raise ApiError(400, "url fehlt oder ungültig")
        return {"result": await self.runs().attach_hub_link(dungeon.strip(), start_ms, url)}


async def setup(bot: Bot) -> None:
    await bot.add_cog(Control(bot))
