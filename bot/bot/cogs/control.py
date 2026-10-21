"""Steuer-API für den NexHub: dieselben Einstellungen wie im Web-Dashboard, aber als JSON.

Läuft als eigener aiohttp-Server im Bot (Port 8790, s. CONTROL_PORT) und startet nur, wenn
`BOT_CONTROL_KEY` gesetzt ist. Jede Anfrage braucht `Authorization: Bearer <BOT_CONTROL_KEY>`.
Gedacht für das interne Docker-Netz auf dem VPS: Der Port wird nie veröffentlicht, nur die
Hub-API (`/api/admin/bot/…`, nur Admins) spricht mit ihm. Wer angemeldet ist und ob er Admin ist,
prüft der Hub; der Bot vertraut dem Schlüssel und schreibt den Namen aus `X-Hub-User` ins
Discord-Audit-Log, wo er etwas am Server ändert.

Die Formular-Bereiche stehen einmal hier in `SECTIONS` (Feldtyp, Beschriftung, Hinweis). Der Hub
zeichnet daraus seine Formulare, ohne die einzelnen Schlüssel zu kennen. Was kein einfaches
Formular ist (Level-Belohnungen, Ankündigungen, eigene Befehle, Benachrichtigungen,
Sichtbarkeits-Matrix, Regel-Text), hat eigene Endpunkte.

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
from dataclasses import dataclass, field
from typing import Any, Awaitable, Callable

import discord
from aiohttp import web
from discord.ext import commands

log = logging.getLogger(__name__)

DEFAULT_PORT = 8790
STARTED = time.time()

TEXT_TYPES = (discord.ChannelType.text, discord.ChannelType.news)
VOICE_TYPES = (discord.ChannelType.voice,)


class ApiError(Exception):
    """Wird zur JSON-Antwort `{"detail": …}` mit diesem Status (wie bei der Hub-API)."""

    def __init__(self, status: int, detail: str):
        super().__init__(detail)
        self.status = status
        self.detail = detail


# ---- Formular-Bereiche ---------------------------------------------------------------------

@dataclass(frozen=True)
class Field:
    """Ein Eingabefeld. `kind`: channel, voice, role, channels, roles, bool, int, text, textarea, choice."""
    key: str
    kind: str
    label: str
    group: str = ""
    hint: str = ""
    default: Any = None
    min: int | None = None
    # int: 0 heißt „aus“ und löscht den Wert, statt 0 zu speichern
    zero_is_off: bool = False
    options: tuple[str, ...] = ()


@dataclass(frozen=True)
class Section:
    id: str
    title: str
    description: str = ""
    fields: tuple[Field, ...] = ()
    # Hinweise unter dem Formular, die nur in Discord gehen
    note: str = ""
    # Aktionen als Knopf (id → Beschriftung); Ausführung in Control.ACTIONS
    actions: dict[str, str] = field(default_factory=dict)


SECTIONS: dict[str, Section] = {s.id: s for s in [
    Section("allgemein", "Allgemein", "Moderation, Begrüßung, Musik und Sprachkanäle.", (
        Field("log_channel", "channel", "Log-Kanal", "Moderation",
              "Gelöschte/bearbeitete Nachrichten, Beitritte, Bans, …"),
        Field("antispam", "bool", "Spamschutz aktiv", "Moderation", default=True),
        Field("allow_invites", "bool", "Einladungslinks erlauben", "Moderation"),
        Field("welcome_channel", "channel", "Willkommenskanal", "Willkommen"),
        Field("welcome_text", "textarea", "Begrüßungstext", "Willkommen",
              "Platzhalter: {user} {name} {server} {anzahl}"),
        Field("autorole", "role", "Autorolle", "Willkommen", "Wird sofort beim Beitritt vergeben, z. B. „Neuling“."),
        Field("dj_role", "role", "DJ-Rolle", "Musik & Voice", "Leer: alle dürfen die Musik steuern."),
        Field("tempvoice_hub", "voice", "Temp-Voice-Kanal", "Musik & Voice",
              "Neu anlegen geht genauer per /setup temp-voice in Discord."),
    )),
    Section("automod", "Automod", "Jeder Verstoß zählt zusätzlich als Verwarnung durch den Bot.", (
        Field("automod_banned_words", "textarea", "Verbotene Wörter", "Wortfilter & Links", "Durch Komma getrennt."),
        Field("automod_link_filter", "bool", "Nur Links zu erlaubten Domains zulassen", "Wortfilter & Links"),
        Field("automod_allowed_domains", "textarea", "Erlaubte Domains", "Wortfilter & Links", "Durch Komma getrennt."),
        Field("automod_caps", "bool", "Nachrichten mit zu vielen Großbuchstaben entfernen", "Großbuchstaben & Emojis"),
        Field("automod_emoji_limit", "int", "Emoji-Grenze pro Nachricht", "Großbuchstaben & Emojis",
              "0 = aus", default=0, min=0, zero_is_off=True),
    )),
    Section("verwarnungen", "Verwarnungen", "Automatische Strafe ab einer Anzahl Verwarnungen.", (
        Field("warn_threshold", "int", "Schwelle", hint="0 = aus", default=0, min=0, zero_is_off=True),
        Field("warn_action", "choice", "Aktion", default="timeout", options=("timeout", "kick", "ban")),
    ), note="Einzelne Verwarnungen laufen über /warn, /warnungen und /warnung-loeschen in Discord."),
    Section("tickets", "Tickets", "Wer neue Tickets sieht und sie schließen darf.", (
        Field("ticket_team_roles", "roles", "Team-Rollen"),
    ), note="Das Panel postet /ticket-panel in Discord."),
    Section("community", "Community", "Zähler, Starboard, Geburtstage und Bump-Erinnerung.", (
        Field("member_count_channel", "voice", "Mitglieder-Zähler", "Statistik-Kanäle"),
        Field("bots_count_channel", "voice", "Bots-Zähler", "Statistik-Kanäle"),
        Field("starboard_channel", "channel", "Highlight-Kanal", "Starboard"),
        Field("starboard_threshold", "int", "Schwelle (Sterne, ohne den des Autors)", "Starboard", default=3, min=1),
        Field("birthday_channel", "channel", "Kanal für die Gratulation um 9 Uhr", "Geburtstage",
              "Mitglieder tragen ihren Geburtstag per /geburtstag-setzen ein."),
        Field("bump_channel", "channel", "Kanal, in dem ihr /bump nutzt", "Bump-Erinnerung (Disboard)"),
        Field("bump_role", "role", "Rolle, die gepingt wird", "Bump-Erinnerung (Disboard)"),
    )),
    Section("level", "Levelsystem", "XP für Nachrichten und Sprachzeit.", (
        Field("level_system_enabled", "bool", "Levelsystem an", "Grundeinstellungen"),
        Field("level_announce_channel", "channel", "Kanal für Level-Up-Nachrichten", "Grundeinstellungen",
              "Leer: im Kanal der Nachricht."),
        Field("voice_xp_per_minute", "int", "XP pro Minute Sprachzeit", "Grundeinstellungen", "0 = aus",
              default=0, min=0, zero_is_off=True),
        Field("level_no_xp_channels", "channels", "Kanäle ohne XP", "Ausnahmen"),
        Field("level_no_xp_roles", "roles", "Rollen ohne XP", "Ausnahmen"),
    )),
    Section("aion", "AION 2", "Runs aus dem NexBoard: ein Post je Lauf mit Rangliste und Link in den NexHub.", (
        Field("aion_channel", "channel", "Ziel-Kanal", hint="Leer schaltet die Posts ab."),
    ), actions={"token": "Neuen Token erzeugen (der alte wird ungültig)"}),
]}


def read_field(db, guild_id: int, f: Field) -> Any:
    if f.kind in ("channel", "voice", "role", "text", "textarea", "choice"):
        return db.get(guild_id, f.key, f.default if f.kind == "choice" else None) or (
            "" if f.kind in ("text", "textarea") else None)
    if f.kind in ("channels", "roles"):
        return [str(i) for i in db.get_ids(guild_id, f.key)]
    if f.kind == "bool":
        return db.get_bool(guild_id, f.key, bool(f.default))
    if f.kind == "int":
        value = db.get_int(guild_id, f.key)
        return f.default if value is None else value
    raise ValueError(f.kind)


def _id(value: Any, label: str) -> int | None:
    if value in (None, ""):
        return None
    if isinstance(value, int) or (isinstance(value, str) and value.isdigit()):
        return int(value)
    raise ApiError(400, f"{label}: ungültige ID")


def convert_field(guild, f: Field, value: Any) -> str | int | bool | None:
    """Wert aus dem Hub prüfen und in die Form bringen, die `db.set` speichert (None löscht)."""
    if f.kind in ("channel", "voice"):
        cid = _id(value, f.label)
        if cid is not None:
            ch = guild.get_channel(cid)
            if ch is None or ch.type not in (VOICE_TYPES if f.kind == "voice" else TEXT_TYPES):
                raise ApiError(400, f"{f.label}: Kanal gibt es nicht")
        return cid
    if f.kind == "role":
        rid = _id(value, f.label)
        if rid is not None and guild.get_role(rid) is None:
            raise ApiError(400, f"{f.label}: Rolle gibt es nicht")
        return rid
    if f.kind in ("channels", "roles"):
        if not isinstance(value, list):
            raise ApiError(400, f"{f.label}: Liste erwartet")
        ids = [_id(v, f.label) for v in value]
        lookup = guild.get_channel if f.kind == "channels" else guild.get_role
        if any(i is None or lookup(i) is None for i in ids):
            raise ApiError(400, f"{f.label}: unbekannter Eintrag")
        return ",".join(str(i) for i in dict.fromkeys(ids)) or None
    if f.kind == "bool":
        if not isinstance(value, bool):
            raise ApiError(400, f"{f.label}: ja/nein erwartet")
        return value
    if f.kind == "int":
        if isinstance(value, bool) or not isinstance(value, int):
            raise ApiError(400, f"{f.label}: Zahl erwartet")
        if f.min is not None and value < f.min:
            raise ApiError(400, f"{f.label}: mindestens {f.min}")
        return None if f.zero_is_off and value == 0 else value
    if f.kind in ("text", "textarea"):
        if not isinstance(value, str):
            raise ApiError(400, f"{f.label}: Text erwartet")
        return value.strip()[:4000] or None
    if f.kind == "choice":
        if value not in f.options:
            raise ApiError(400, f"{f.label}: nur {', '.join(f.options)}")
        return value
    raise ValueError(f.kind)


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
    return {"id": str(guild.id), "name": guild.name,
            "icon_url": str(guild.icon.url) if guild.icon else None,
            "members": guild.member_count or len(guild.members), "channels": channels, "roles": roles}


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
        r.add_get("/control/notifications", self.notifications)
        r.add_post("/control/notifications/{id}/toggle", self.notification_toggle)
        r.add_delete("/control/notifications/{id}", self.notification_delete)
        r.add_get("/control/matrix", self.matrix)
        r.add_put("/control/matrix", self.matrix_set)
        r.add_post("/control/run-link", self.run_link)
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

    def section_info(self, guild, s: Section) -> list[dict]:
        """Nur-Lese-Angaben unter einem Formular, z. B. Adresse und Token für das NexBoard."""
        if s.id == "aion":
            aion = self.bot.get_cog("AionDedup")
            return [
                {"label": "Endpunkt", "value": aion.api_url() if aion else None, "code": True},
                {"label": "Token", "value": self.db.get(guild.id, "aion_api_token"), "code": True, "secret": True},
            ]
        return []

    def section_out(self, guild, s: Section) -> dict:
        return {
            "id": s.id, "title": s.title, "description": s.description, "note": s.note,
            "fields": [{"key": f.key, "kind": f.kind, "label": f.label, "group": f.group, "hint": f.hint,
                        "min": f.min, "options": list(f.options), "value": read_field(self.db, guild.id, f)}
                       for f in s.fields],
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
        by_key = {f.key: f for f in s.fields}
        unknown = set(values) - set(by_key)
        if unknown:
            raise ApiError(400, f"Unbekannte Felder: {', '.join(sorted(unknown))}")
        # Erst alles prüfen, dann speichern: ein ungültiges Feld lässt den Bereich unverändert
        converted = {k: convert_field(guild, by_key[k], v) for k, v in values.items()}
        for key, value in converted.items():
            await self.db.set(guild.id, key, value)
        if s.id == "verwarnungen" and self.db.get_int(guild.id, "warn_threshold") is None:
            await self.db.set(guild.id, "warn_action", None)
        if s.id == "community" and (stats := self.bot.get_cog("Stats")):
            await stats.update_guild(guild)
        return self.section_out(guild, s)

    async def section_action(self, request: web.Request) -> dict:
        guild = self.guild()
        s = self._section(request)
        action = request.match_info["action"]
        if action not in s.actions:
            raise ApiError(404, "Aktion gibt es nicht")
        if (s.id, action) == ("aion", "token"):
            import secrets

            await self.db.set(guild.id, "aion_api_token", secrets.token_urlsafe(24))
        return self.section_out(guild, s)

    # ---- Verifizierung -------------------------------------------------------------------------

    async def verification(self, request: web.Request) -> dict:
        guild = self.guild()
        channel = guild.get_channel(self.db.get_int(guild.id, "verify_channel") or 0)
        role = guild.get_role(self.db.get_int(guild.id, "verify_role") or 0)
        text = None
        message_id = self.db.get_int(guild.id, "verify_message")
        if channel and message_id:
            try:
                message = await channel.fetch_message(message_id)
                text = message.embeds[0].description if message.embeds else None
            except discord.HTTPException:
                message_id = None
        return {"channel": channel.name if channel else None, "role": role.name if role else None,
                "panel": bool(channel and message_id), "text": text}

    async def verification_text(self, request: web.Request) -> None:
        guild = self.guild()
        text = str((await self.body(request)).get("text") or "").strip()
        if not text:
            raise ApiError(400, "Kein Text")
        if len(text) > 4096:
            raise ApiError(400, "Höchstens 4096 Zeichen (Discord-Grenze)")
        channel = guild.get_channel(self.db.get_int(guild.id, "verify_channel") or 0)
        message_id = self.db.get_int(guild.id, "verify_message")
        if not channel or not message_id:
            raise ApiError(409, "Noch kein Regel-Panel – erst /setup verifizierung in Discord")
        message = await channel.fetch_message(message_id)
        embed = message.embeds[0] if message.embeds else discord.Embed(title="📜 Regeln")
        embed.description = text
        await message.edit(embed=embed)

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
        role_id = _id((await self.body(request)).get("role_id"), "Rolle")
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

    # ---- Benachrichtigungen --------------------------------------------------------------------

    async def notifications(self, request: web.Request) -> list[dict]:
        from ..notify.manager import PROVIDERS

        guild = self.guild()
        out = []
        for f in await self.db.fetchall("SELECT * FROM feeds WHERE guild_id=? ORDER BY id", (guild.id,)):
            provider = PROVIDERS.get(f["kind"])
            events = json.loads(f["events"] or "[]")
            ch = guild.get_channel(f["channel_id"])
            out.append({
                "id": f["id"], "kind": provider.label if provider else f["kind"], "source": f["source"],
                "events": [provider.events.get(e, e) if provider else e for e in events],
                "channel": ch.name if ch else None, "enabled": bool(f["enabled"]), "error": f["error"],
            })
        return out

    async def _feed(self, request: web.Request):
        guild = self.guild()
        feed_id = request.match_info["id"]
        row = await self.db.fetchone("SELECT id, enabled FROM feeds WHERE id=? AND guild_id=?",
                                     (int(feed_id) if feed_id.isdigit() else -1, guild.id))
        if row is None:
            raise ApiError(404, "Benachrichtigung gibt es nicht")
        return row

    async def notification_toggle(self, request: web.Request) -> list[dict]:
        row = await self._feed(request)
        await self.db.execute("UPDATE feeds SET enabled=? WHERE id=?", (0 if row["enabled"] else 1, row["id"]))
        return await self.notifications(request)

    async def notification_delete(self, request: web.Request) -> None:
        row = await self._feed(request)
        await self.db.execute("DELETE FROM feeds WHERE id=?", (row["id"],))

    # ---- Sichtbarkeits-Matrix ------------------------------------------------------------------

    async def matrix(self, request: web.Request) -> dict:
        return matrix(self.guild())

    async def matrix_set(self, request: web.Request) -> dict:
        """Eine Zelle umschalten: diese Rolle darf den Kanal sehen (`allow`) oder nicht."""
        guild = self.guild()
        data = await self.body(request)
        channel = guild.get_channel(_id(data.get("channel_id"), "Kanal") or 0)
        role = guild.get_role(_id(data.get("role_id"), "Rolle") or 0)
        if channel is None or role is None or role.is_default() or role.managed:
            raise ApiError(400, "Kanal oder Rolle gibt es nicht")
        if not isinstance(data.get("allow"), bool):
            raise ApiError(400, "allow: ja/nein erwartet")
        await channel.set_permissions(role, view_channel=data["allow"], reason=self.reason(request))
        return matrix(guild)

    # ---- Runs aus dem Hub ---------------------------------------------------------------------

    async def run_link(self, request: web.Request) -> dict:
        """Der Hub hat einen Run gespeichert: Link an den passenden AION-Post (aion_dedup.attach_hub_link)."""
        data = await self.body(request)
        dungeon, start_ms, url = data.get("dungeon"), data.get("start_ms"), data.get("url")
        if not isinstance(dungeon, str) or not dungeon.strip():
            raise ApiError(400, "dungeon fehlt")
        if not isinstance(start_ms, int) or isinstance(start_ms, bool):
            raise ApiError(400, "start_ms fehlt")
        if not isinstance(url, str) or not url.startswith(("https://", "http://")) or len(url) > 500:
            raise ApiError(400, "url fehlt oder ungültig")
        aion = self.bot.get_cog("AionDedup")
        if aion is None:
            raise ApiError(503, "AION-Modul ist nicht geladen")
        return {"result": await aion.attach_hub_link(dungeon.strip(), start_ms, url)}


async def setup(bot) -> None:
    await bot.add_cog(Control(bot))
