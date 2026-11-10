"""Einstellungs-Bereiche: welche Felder zusammen auf einer Seite stehen, und wie sie gelesen, geprüft
und gespeichert werden. Eine Stelle für Hub-Formular (admin/control.py), Klick-Panel (panel.py) und
`/setup ändern` (admin/setup.py).

Die Felder kommen aus den Settings-Modellen der Module (`bot.core.schema.setting`). Gespeichert wird
wie bisher ein Eintrag je Feld in der Tabelle settings. Nach dem Speichern meldet der Bot das
Discord-Ereignis `settings_changed(guild, section_id)`, damit Teile wie die Zähler-Kanäle reagieren,
ohne dass hier jemand sie kennt.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

import discord
from pydantic import BaseModel

from .core.schema import form_fields
from .db import Database
from .hubpages import TEXT_TYPES, VOICE_TYPES, ApiError, Field
from .modules.aion2.runs.settings import RunPostSettings
from .modules.aion2.schedule.settings import ScheduleSettings
from .modules.community.birthdays.settings import BirthdaySettings
from .modules.community.bump.settings import BumpSettings
from .modules.community.levels.settings import LevelSettings
from .modules.community.starboard.settings import StarboardSettings
from .modules.moderation.antispam.settings import AntispamSettings
from .modules.moderation.automod.settings import AutomodSettings
from .modules.moderation.log.settings import LogSettings
from .modules.moderation.tickets.settings import TicketSettings
from .modules.moderation.warnings.settings import WarningSettings
from .modules.music.player.settings import PlayerSettings
from .modules.server.counters.settings import CounterSettings
from .modules.server.tempvoice.settings import TempVoiceSettings
from .modules.server.welcome.settings import WelcomeSettings

MAX_TEXT = 4000  # längster gespeicherter Text (Discord-Nachrichten haben höchstens 4000 Zeichen)


@dataclass(frozen=True)
class Section:
    id: str
    title: str
    description: str
    models: tuple[type[BaseModel], ...]
    # Hinweise unter dem Formular, die nur in Discord gehen
    note: str = ""
    # Aktionen als Knopf (id → Beschriftung); Ausführung in Control.section_action
    actions: dict[str, str] = field(default_factory=dict)

    @property
    def fields(self) -> tuple[Field, ...]:
        return tuple(f for model in self.models for f in form_fields(model))

    def groups(self) -> list[tuple[str, tuple[Field, ...]]]:
        """Felder nach Gruppe, in der Reihenfolge des ersten Auftretens (eine Panel-Seite je Gruppe)."""
        order: dict[str, list[Field]] = {}
        for f in self.fields:
            order.setdefault(f.group, []).append(f)
        return [(name, tuple(fields)) for name, fields in order.items()]


SECTIONS: dict[str, Section] = {s.id: s for s in [
    Section("allgemein", "Allgemein", "Moderation, Begrüßung, Musik und Sprachkanäle.",
            (LogSettings, AntispamSettings, WelcomeSettings, PlayerSettings, TempVoiceSettings)),
    Section("automod", "Automod", "Jeder Verstoß zählt zusätzlich als Verwarnung durch den Bot.",
            (AutomodSettings,)),
    Section("verwarnungen", "Verwarnungen", "Automatische Strafe ab einer Anzahl Verwarnungen.",
            (WarningSettings,),
            note="Einzelne Verwarnungen laufen über /warn, /warnungen und /warnung-loeschen in Discord."),
    Section("tickets", "Tickets", "Wer neue Tickets sieht und sie schließen darf.", (TicketSettings,),
            note="Das Panel postet /ticket-panel in Discord."),
    Section("community", "Community", "Zähler, Starboard, Geburtstage und Bump-Erinnerung.",
            (CounterSettings, StarboardSettings, BirthdaySettings, BumpSettings)),
    Section("level", "Levelsystem", "XP für Nachrichten und Sprachzeit.", (LevelSettings,)),
    Section("aion", "AION 2", "Runs aus dem NexBoard (ein Post je Lauf mit Rangliste und Link in den NexHub) "
            "und die Termin-Tafel.", (RunPostSettings, ScheduleSettings),
            actions={"token": "Neuen Token erzeugen (der alte wird ungültig)"}),
]}


def find_field(key: str) -> tuple[Section, Field] | None:
    for section in SECTIONS.values():
        for f in section.fields:
            if f.key == key:
                return section, f
    return None


def read_field(db: Database, guild_id: int, f: Field) -> Any:
    """Gespeicherter Wert in der Form, die Hub und Panel anzeigen (IDs als Text)."""
    if f.kind in ("channel", "voice", "role", "text", "textarea", "choice"):
        stored = db.get(guild_id, f.key, f.default if f.kind == "choice" else None)
        return stored or ("" if f.kind in ("text", "textarea") else None)
    if f.kind in ("channels", "roles"):
        return [str(i) for i in db.get_ids(guild_id, f.key)]
    if f.kind == "bool":
        return db.get_bool(guild_id, f.key, bool(f.default))
    if f.kind == "int":
        value = db.get_int(guild_id, f.key)
        return f.default if value is None else value
    raise ValueError(f.kind)


def parse_id(value: Any, label: str) -> int | None:
    if value in (None, ""):
        return None
    if isinstance(value, int) or (isinstance(value, str) and value.isdigit()):
        return int(value)
    raise ApiError(400, f"{label}: ungültige ID")


def convert_field(guild: discord.Guild, f: Field, value: Any) -> str | int | bool | None:
    """Eingabe prüfen und in die Form bringen, die `db.set` speichert (None löscht)."""
    if f.kind in ("channel", "voice"):
        return check_channel(guild, f, parse_id(value, f.label))
    if f.kind == "role":
        rid = parse_id(value, f.label)
        if rid is not None and guild.get_role(rid) is None:
            raise ApiError(400, f"{f.label}: Rolle gibt es nicht")
        return rid
    if f.kind in ("channels", "roles"):
        return convert_id_list(guild, f, value)
    if f.kind == "bool":
        if not isinstance(value, bool):
            raise ApiError(400, f"{f.label}: ja/nein erwartet")
        return value
    if f.kind == "int":
        return convert_int(f, value)
    if f.kind in ("text", "textarea"):
        if not isinstance(value, str):
            raise ApiError(400, f"{f.label}: Text erwartet")
        return value.strip()[:MAX_TEXT] or None
    if f.kind == "choice":
        if value not in dict(f.choices()):
            raise ApiError(400, f"{f.label}: nur {', '.join(dict(f.choices()))}")
        return str(value)
    raise ValueError(f.kind)


def check_channel(guild: discord.Guild, f: Field, cid: int | None) -> int | None:
    if cid is None:
        return None
    channel = guild.get_channel(cid)
    if channel is None or channel.type not in (VOICE_TYPES if f.kind == "voice" else TEXT_TYPES):
        raise ApiError(400, f"{f.label}: Kanal gibt es nicht")
    return cid


def convert_id_list(guild: discord.Guild, f: Field, value: Any) -> str | None:
    if not isinstance(value, list):
        raise ApiError(400, f"{f.label}: Liste erwartet")
    ids = [parse_id(v, f.label) for v in value]
    lookup = guild.get_channel if f.kind == "channels" else guild.get_role
    if any(i is None or lookup(i) is None for i in ids):
        raise ApiError(400, f"{f.label}: unbekannter Eintrag")
    return ",".join(str(i) for i in dict.fromkeys(ids)) or None


def convert_int(f: Field, value: Any) -> int | None:
    if isinstance(value, bool) or not isinstance(value, int):
        raise ApiError(400, f"{f.label}: Zahl erwartet")
    if f.min is not None and value < f.min:
        raise ApiError(400, f"{f.label}: mindestens {f.min}")
    return None if f.zero_is_off and value == 0 else value


async def save_values(client: discord.Client, db: Database, guild: discord.Guild, section: Section,
                      values: dict[str, Any]) -> None:
    """Felder eines Bereichs speichern. Erst alles prüfen, dann speichern: ein ungültiges Feld lässt
    den Bereich unverändert (ApiError). Fehlende Felder bleiben, wie sie sind."""
    by_key = {f.key: f for f in section.fields}
    unknown = set(values) - set(by_key)
    if unknown:
        raise ApiError(400, f"Unbekannte Felder: {', '.join(sorted(unknown))}")
    converted = {key: convert_field(guild, by_key[key], value) for key, value in values.items()}
    for key, stored in converted.items():
        await db.set(guild.id, key, stored)
    client.dispatch("settings_changed", guild, section.id)
