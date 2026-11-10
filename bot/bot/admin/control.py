"""Steuer-API für den NexHub: dieselben Einstellungen wie im Web-Dashboard, aber als JSON.

Hängt am internen Teil des WebHost (bot/core/web.py, Port 8790), der nur mit `BOT_CONTROL_KEY`
startet und jede Anfrage mit `Authorization: Bearer <BOT_CONTROL_KEY>` prüft.
Gedacht für das interne Docker-Netz auf dem VPS: Der Port wird nie veröffentlicht, nur die
Hub-API (`/api/admin/bot/…`, nur Admins) spricht mit ihm. Wer angemeldet ist und ob er Admin ist,
prüft der Hub; der Bot vertraut dem Schlüssel und schreibt den Namen aus `X-Hub-User` ins
Discord-Audit-Log, wo er etwas am Server ändert.

Menü und Seiten des Hubs kommen aus `/control/pages`: Formular-Bereiche aus `SECTIONS`, dazu was
jedes Modul per `pages()` beschreibt (Tabellen, Status, Aktionen, siehe `bot/hubpages.py`). Der
Hub zeichnet das allgemein, ohne die einzelnen Funktionen zu kennen. Seiten mit eigener Oberfläche
im Hub bringen ihre Endpunkte selbst mit (`routes()` im Modul: Level-Belohnungen, Ankündigungen,
eigene Befehle, Regel-Text, Run-Link); hier stehen nur Status, Server, Formulare, Seiten und die
Sichtbarkeits-Matrix, die zu keinem Modul gehört.

Discord-IDs gehen als Strings raus und rein: JavaScript rechnet mit Gleitkommazahlen und würde
die letzten Stellen einer 18-stelligen ID verfälschen.
"""

from __future__ import annotations

import logging
import os
import time
from typing import TYPE_CHECKING, Any

import discord
from aiohttp import web

from .. import hubpages
from ..core.web import RouteTable, audit_reason, find_guild, hub_guild, hub_user, json_body
from ..errors import UserError
from ..forms import SECTIONS, Section, parse_id, read_field, save_values
from ..hubpages import ApiError, Ctx, Form, Page
from ..modules.aion2.runs import RunPosts

if TYPE_CHECKING:
    from ..__main__ import Bot

log = logging.getLogger(__name__)

STARTED = time.time()

TEXT_TYPES = hubpages.TEXT_TYPES
VOICE_TYPES = hubpages.VOICE_TYPES


# ---- Formular-Bereiche ---------------------------------------------------------------------

# Seiten, die zu keinem Modul gehören: Übersicht, Sichtbarkeit und die Formular-Bereiche aus
# forms.SECTIONS. Alles andere liefern die Module per pages() (siehe hubpages.py).
CORE_PAGES: tuple[Page, ...] = (
    Page("", "Übersicht", "Server", order=0, custom=True),
    Page("allgemein", "Allgemein", "Server", (Form("allgemein"),), SECTIONS["allgemein"].description, order=10),
    Page("tickets", "Tickets", "Server", (Form("tickets"),), SECTIONS["tickets"].description, order=30),
    Page("sichtbarkeit", "Sichtbarkeit", "Server", order=40, custom=True),
    Page("community", "Community", "Community", (Form("community"),), SECTIONS["community"].description, order=10),
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


class ControlApi:
    """Grundgerüst der Steuer-API; die Routen hängt der Host beim Start in den WebHost."""

    def __init__(self, bot: Bot) -> None:
        self.bot = bot
        self.db = bot.db

    def routes(self, r: RouteTable) -> None:
        r.control("GET", "/control/status", self.status)
        r.control("GET", "/control/guild", self.guild_data)
        r.control("GET", "/control/sections", self.sections)
        r.control("PUT", "/control/sections/{id}", self.save_section)
        r.control("POST", "/control/sections/{id}/actions/{action}", self.section_action)
        r.control("GET", "/control/matrix", self.matrix)
        r.control("PUT", "/control/matrix", self.matrix_set)
        r.control("GET", "/control/pages", self.pages)
        r.control("GET", "/control/pages/{page}", self.page)
        r.control("POST", "/control/pages/{page}/{block}/{action}", self.page_action)

    def guild(self) -> discord.Guild:
        return hub_guild(self.bot)

    # ---- Status und Server ---------------------------------------------------------------------

    async def status(self, request: web.Request) -> dict[str, Any]:
        user = self.bot.user
        guild = find_guild(self.bot)
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
        values = (await json_body(request)).get("values")
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

    # ---- Sichtbarkeits-Matrix ------------------------------------------------------------------

    async def matrix(self, request: web.Request) -> dict[str, Any]:
        return matrix(self.guild())

    async def matrix_set(self, request: web.Request) -> dict[str, Any]:
        """Eine Zelle umschalten: diese Rolle darf den Kanal sehen (`allow`) oder nicht."""
        guild = self.guild()
        data = await json_body(request)
        channel = guild.get_channel(parse_id(data.get("channel_id"), "Kanal") or 0)
        role = guild.get_role(parse_id(data.get("role_id"), "Rolle") or 0)
        if channel is None or role is None or role.is_default() or role.managed:
            raise ApiError(400, "Kanal oder Rolle gibt es nicht")
        if not isinstance(data.get("allow"), bool):
            raise ApiError(400, "allow: ja/nein erwartet")
        await channel.set_permissions(role, view_channel=data["allow"], reason=audit_reason(request))
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
        uid = request.headers.get("X-Hub-User-Id", "")
        return Ctx(self.bot, self.guild(), hub_user(request), int(uid) if uid.isdigit() else None)

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
        data = await json_body(request)
        values = hubpages.action_values(ctx.guild, action.fields, data.get("values"))
        item = data.get("item")
        try:
            message = await action.run(ctx, values, str(item) if item is not None else None)
        except UserError as e:
            raise ApiError(400, str(e)) from None
        log.info("Hub-Aktion %s/%s/%s von %s", page.id, request.match_info["block"], action.id, ctx.who or "?")
        out = await hubpages.page_out(ctx, page, lambda sid: self.section_out(ctx.guild, SECTIONS[sid]))
        return {"message": message or "Erledigt.", "page": out}
