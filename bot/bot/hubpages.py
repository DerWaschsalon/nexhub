"""Seiten für den NexHub: Jeder Cog beschreibt selbst, was der Bereich „Bot“ im Hub von ihm zeigt.

Ein Cog mit einer Methode `hub_pages(self) -> list[Page]` taucht automatisch im Menü des Hubs auf,
der Hub kennt keine einzelnen Funktionen. Eine Seite besteht aus Blöcken:

- `Form`: ein Formular-Bereich aus `control.SECTIONS` (Einstellungen, gespeichert über die DB).
- `Table`: eine Liste (Zeilen mit `id`), optional mit „Neu anlegen“ (`create`) und Aktionen je Zeile.
- `Status`: Kennzahlen als Bezeichnung/Wert, optional mit Aktionen.
- `Actions`: nur Knöpfe, jeder optional mit eigenem kleinen Formular.

Aktionen bekommen einen `Ctx` (Server, wer im Hub geklickt hat) und die geprüften Werte ihrer
Felder und geben eine kurze Rückmeldung zurück. `UserError`/`ApiError` werden zur Fehlermeldung im
Hub. Wie die Steuer-API das ausliefert, steht in `cogs/control.py` (`/control/pages…`).

Neue Funktion im Bot = `hub_pages()` im Cog ergänzen, im Hub ist nichts zu tun.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Awaitable, Callable

import discord

# Menü-Gruppen im Hub, in dieser Reihenfolge; unbekannte Gruppen kommen ans Ende
GROUPS = ("Server", "Community", "Moderation", "Musik", "Benachrichtigungen", "Spiele", "System")

TEXT_TYPES = (discord.ChannelType.text, discord.ChannelType.news)
VOICE_TYPES = (discord.ChannelType.voice, discord.ChannelType.stage_voice)


class ApiError(Exception):
    """Wird zur JSON-Antwort `{"detail": …}` mit diesem Status (wie bei der Hub-API)."""

    def __init__(self, status: int, detail: str):
        super().__init__(detail)
        self.status = status
        self.detail = detail


@dataclass(frozen=True)
class Field:
    """Ein Eingabefeld. `kind`: channel, voice, role, member, channels, roles, multi, bool, int,
    text, textarea, choice. `options` für choice/multi: Werte oder (Wert, Beschriftung).
    `show_if=(schlüssel, (wert, …))`: nur sichtbar und gültig, wenn ein anderes Feld so steht."""
    key: str
    kind: str
    label: str
    group: str = ""
    hint: str = ""
    default: Any = None
    min: int | None = None
    max: int | None = None
    # int: 0 heißt „aus“ und löscht den Wert, statt 0 zu speichern
    zero_is_off: bool = False
    options: tuple = ()
    required: bool = False
    show_if: tuple[str, tuple[str, ...]] | None = None

    def choices(self) -> list[tuple[str, str]]:
        return [(o, o) if isinstance(o, str) else (str(o[0]), str(o[1])) for o in self.options]

    def out(self, value: Any = None) -> dict:
        return {
            "key": self.key, "kind": self.kind, "label": self.label, "group": self.group, "hint": self.hint,
            "min": self.min, "max": self.max, "required": self.required,
            "options": [{"value": v, "label": lbl} for v, lbl in self.choices()],
            "show_if": {"key": self.show_if[0], "values": list(self.show_if[1])} if self.show_if else None,
            "value": self.default if value is None else value,
        }


@dataclass
class Ctx:
    """Wer im Hub was auslöst. `who_id` ist die Discord-ID des Hub-Kontos (kann fehlen)."""
    bot: Any
    guild: discord.Guild
    who: str = ""
    who_id: int | None = None

    @property
    def reason(self) -> str:
        return f"NexHub: {self.who}" if self.who else "NexHub"

    @property
    def member(self) -> discord.Member | None:
        return self.guild.get_member(self.who_id) if self.who_id else None


Runner = Callable[[Ctx, dict, "str | None"], Awaitable["str | None"]]


@dataclass(frozen=True)
class Action:
    id: str
    label: str
    run: Runner  # async (ctx, werte, zeilen_id) -> Rückmeldung
    fields: tuple[Field, ...] = ()
    confirm: str = ""  # Rückfrage vor dem Ausführen
    danger: bool = False
    # Nur für Zeilen, bei denen dieser Schlüssel wahr ist (z. B. "active"); leer = immer
    when: str = ""
    # Beschriftung des Absende-Knopfs im Formular (leer = wie label)
    submit: str = ""

    def out(self) -> dict:
        return {"id": self.id, "label": self.label, "submit": self.submit or self.label,
                "confirm": self.confirm, "danger": self.danger,
                "when": self.when, "fields": [f.out() for f in self.fields]}


@dataclass(frozen=True)
class Column:
    """`kind`: text, num, time (Unix-Sekunden), date, badge (Text mit `ok`/`warn`/`danger` in
    `<key>_tone`), link."""
    key: str
    label: str
    kind: str = "text"


@dataclass(frozen=True)
class Form:
    section: str  # id in control.SECTIONS


@dataclass(frozen=True)
class Table:
    id: str
    title: str
    columns: tuple[Column, ...]
    rows: Callable[[Ctx], Awaitable[list[dict]]]
    create: Action | None = None
    actions: tuple[Action, ...] = ()
    empty: str = "Noch nichts da."
    description: str = ""


@dataclass(frozen=True)
class Status:
    id: str
    title: str
    # [{"label": …, "value": …, "href"?: …}]; Einträge ohne label sind Schalter für Action.when
    items: Callable[[Ctx], Awaitable[list[dict]]]
    actions: tuple[Action, ...] = ()
    description: str = ""


@dataclass(frozen=True)
class Actions:
    id: str
    title: str
    actions: tuple[Action, ...]
    description: str = ""


Block = Form | Table | Status | Actions


@dataclass(frozen=True)
class Page:
    id: str
    title: str
    group: str
    blocks: tuple = ()
    description: str = ""
    order: int = 100
    # True: eigene Seite im Hub (routes/hub/admin/bot/<id>), der Bot liefert nur den Menüeintrag
    custom: bool = False

    def nav(self) -> dict:
        return {"id": self.id, "title": self.title, "group": self.group, "order": self.order, "custom": self.custom}

    def action(self, block_id: str, action_id: str) -> Action:
        for b in self.blocks:
            if getattr(b, "id", None) != block_id:
                continue
            candidates = [*getattr(b, "actions", ())]
            if isinstance(b, Table) and b.create:
                candidates.append(b.create)
            for a in candidates:
                if a.id == action_id:
                    return a
        raise ApiError(404, "Aktion gibt es nicht")


def group_rank(group: str) -> int:
    return GROUPS.index(group) if group in GROUPS else len(GROUPS)


def ts(dt: datetime | float | None) -> float | None:
    if dt is None:
        return None
    return dt.timestamp() if isinstance(dt, datetime) else float(dt)


def now() -> float:
    return datetime.now(timezone.utc).timestamp()


# ---- Werte aus dem Hub prüfen ----------------------------------------------------------------

def _id(value: Any, label: str) -> int | None:
    if value in (None, ""):
        return None
    if isinstance(value, int) and not isinstance(value, bool) or (isinstance(value, str) and value.isdigit()):
        return int(value)
    raise ApiError(400, f"{label}: ungültige ID")


def visible(f: Field, values: dict) -> bool:
    return f.show_if is None or str(values.get(f.show_if[0]) or "") in f.show_if[1]


def action_values(guild: discord.Guild, fields: tuple[Field, ...], values: Any) -> dict:
    """Werte einer Aktion prüfen und als Python-Objekte liefern (Kanal, Rolle, Mitglied, Zahl, …).
    Ausgeblendete Felder (`show_if`) fallen weg; Pflichtfelder müssen gesetzt sein."""
    if not isinstance(values, dict):
        values = {}
    out: dict[str, Any] = {}
    for f in fields:
        if not visible(f, values):
            continue
        v = values.get(f.key)
        empty = v in (None, "", []) and f.kind not in ("bool", "int")
        if empty or (f.kind == "int" and v in (None, "")):
            if f.required:
                raise ApiError(400, f"{f.label}: bitte ausfüllen")
            out[f.key] = f.default if f.kind in ("int", "bool", "choice") else ([] if f.kind in ("multi", "channels", "roles") else None)
            continue
        if f.kind in ("channel", "voice"):
            ch = guild.get_channel(_id(v, f.label) or 0)
            if ch is None or ch.type not in (VOICE_TYPES if f.kind == "voice" else TEXT_TYPES):
                raise ApiError(400, f"{f.label}: Kanal gibt es nicht")
            out[f.key] = ch
        elif f.kind == "role":
            role = guild.get_role(_id(v, f.label) or 0)
            if role is None:
                raise ApiError(400, f"{f.label}: Rolle gibt es nicht")
            out[f.key] = role
        elif f.kind == "member":
            member = guild.get_member(_id(v, f.label) or 0)
            if member is None:
                raise ApiError(400, f"{f.label}: Mitglied gibt es nicht (mehr)")
            out[f.key] = member
        elif f.kind == "bool":
            if not isinstance(v, bool):
                raise ApiError(400, f"{f.label}: ja/nein erwartet")
            out[f.key] = v
        elif f.kind == "int":
            if isinstance(v, bool) or not isinstance(v, int):
                raise ApiError(400, f"{f.label}: Zahl erwartet")
            if f.min is not None and v < f.min:
                raise ApiError(400, f"{f.label}: mindestens {f.min}")
            if f.max is not None and v > f.max:
                raise ApiError(400, f"{f.label}: höchstens {f.max}")
            out[f.key] = v
        elif f.kind in ("text", "textarea"):
            if not isinstance(v, str):
                raise ApiError(400, f"{f.label}: Text erwartet")
            out[f.key] = v.strip()[:4000]
            if f.required and not out[f.key]:
                raise ApiError(400, f"{f.label}: bitte ausfüllen")
        elif f.kind == "choice":
            if str(v) not in dict(f.choices()):
                raise ApiError(400, f"{f.label}: ungültige Auswahl")
            out[f.key] = str(v)
        elif f.kind == "multi":
            allowed = dict(f.choices())
            if not isinstance(v, list) or any(str(x) not in allowed for x in v):
                raise ApiError(400, f"{f.label}: ungültige Auswahl")
            out[f.key] = [str(x) for x in dict.fromkeys(v)]
            if f.required and not out[f.key]:
                raise ApiError(400, f"{f.label}: mindestens eins auswählen")
        else:
            raise ValueError(f.kind)
    return out


# ---- Ausliefern ------------------------------------------------------------------------------

async def block_out(ctx: Ctx, block: Block, section_out: Callable[[str], dict]) -> dict:
    if isinstance(block, Form):
        return {"type": "form", "id": block.section, "section": section_out(block.section)}
    if isinstance(block, Table):
        return {"type": "table", "id": block.id, "title": block.title, "description": block.description,
                "columns": [{"key": c.key, "label": c.label, "kind": c.kind} for c in block.columns],
                "rows": await block.rows(ctx), "create": block.create.out() if block.create else None,
                "actions": [a.out() for a in block.actions], "empty": block.empty}
    if isinstance(block, Status):
        # Einträge ohne `label` sind Schalter für `Action.when` (z. B. {"paused": True}), keine Anzeige
        items, flags = [], {}
        for it in await block.items(ctx):
            (items.append(it) if "label" in it else flags.update(it))
        return {"type": "status", "id": block.id, "title": block.title, "description": block.description,
                "items": items, "flags": flags, "actions": [a.out() for a in block.actions]}
    if isinstance(block, Actions):
        return {"type": "actions", "id": block.id, "title": block.title, "description": block.description,
                "actions": [a.out() for a in block.actions]}
    raise TypeError(block)


async def page_out(ctx: Ctx, page: Page, section_out: Callable[[str], dict]) -> dict:
    return {**page.nav(), "description": page.description,
            "blocks": [await block_out(ctx, b, section_out) for b in page.blocks]}


def user_label(guild: discord.Guild, user_id: int | None) -> str:
    if not user_id:
        return "–"
    m = guild.get_member(user_id)
    return m.display_name if m else str(user_id)


def channel_label(guild: discord.Guild, channel_id: int | None) -> str:
    ch = guild.get_channel(channel_id) if channel_id else None
    return f"#{ch.name}" if ch else "–"
