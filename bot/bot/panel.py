"""Klick-Panel für Einstellungen, erzeugt aus den Schemas der Module (forms.SECTIONS).

Je Gruppe eines Bereichs gibt es eine Seite. Kanäle und Rollen wählt man aus einer Liste (leer
abwählen schaltet aus), Ja/Nein über einen Umschalter, Zahlen und Texte in einem Formular. Gespeichert
wird über forms.save_values, also genauso geprüft wie im Hub. Was nicht in ein Schema passt (Kanal
anlegen, Token zeigen), hängt der Aufrufer als `extras` an eine Seite.
"""

from __future__ import annotations

from collections.abc import Callable, Coroutine
from typing import Any

import discord

from .db import Database
from .forms import SECTIONS, Section, read_field, save_values
from .hubpages import ApiError, Field

TIMEOUT_S = 180  # ephemere Panels laufen nach drei Minuten ab
MAX_LIST = 25  # Discord: höchstens 25 Einträge in einer Auswahl
MAX_MODAL_INPUTS = 5  # Discord: höchstens 5 Eingabefelder in einem Formular
MODAL_KINDS = ("int", "text", "textarea")
MAX_SHOWN_TEXT = 200  # so viel Text zeigt die Übersicht

# Was der Zurück-Knopf einer Seite tut (zurück ins Hauptmenü)
Back = Callable[[discord.Interaction], Coroutine[Any, Any, None]]


def fmt_value(guild: discord.Guild, f: Field, value: Any) -> str:
    if value in (None, "", []):
        return "–"
    if f.kind in ("channel", "voice"):
        channel = guild.get_channel(int(value))
        return channel.mention if channel else f"(gelöscht: {value})"
    if f.kind == "role":
        role = guild.get_role(int(value))
        return role.mention if role else f"(gelöscht: {value})"
    if f.kind in ("channels", "roles"):
        return ", ".join(fmt_value(guild, Field("x", f.kind[:-1], ""), v) for v in value)
    if f.kind == "bool":
        return "an" if value else "aus"
    if f.kind == "int" and f.zero_is_off and value == 0:
        return "aus"
    text = str(value)
    return text if len(text) <= MAX_SHOWN_TEXT else text[:MAX_SHOWN_TEXT] + " …"


def section_text(db: Database, guild: discord.Guild, section: Section) -> str:
    lines = [f"{f.label}: {fmt_value(guild, f, read_field(db, guild.id, f))}" for f in section.fields]
    return "\n".join(lines)


def overview_embed(db: Database, guild: discord.Guild) -> discord.Embed:
    """Alle Einstellungen auf einen Blick, je Bereich ein Feld."""
    e = discord.Embed(title=f"⚙️ Einstellungen für {guild.name}", colour=discord.Colour.blurple())
    for section in SECTIONS.values():
        e.add_field(name=section.title, value=section_text(db, guild, section)[:1024], inline=False)
    return e


def page_id(section: Section, index: int) -> str:
    return f"{section.id}:{index}"


def page_title(section: Section, group: str) -> str:
    return f"{section.title}: {group}" if group else section.title


def ids_of(f: Field, value: Any) -> list[int]:
    many = f.kind in ("channels", "roles")
    return [int(v) for v in (value if many else [value]) if v]


def chosen(f: Field, ids: list[str]) -> Any:
    """Gewählte IDs in der Form, die forms.save_values erwartet."""
    if f.kind in ("channels", "roles"):
        return ids
    return ids[0] if ids else None


def limits(f: Field) -> dict[str, Any]:
    many = f.kind in ("channels", "roles")
    return {"placeholder": f.label, "min_values": 0, "max_values": MAX_LIST if many else 1,
            "custom_id": f"setup:{f.key}"}


class FieldChannelSelect(discord.ui.ChannelSelect["FieldPage"]):
    """Kanal oder Kanäle, vorbelegt mit dem gespeicherten Wert; alles abwählen schaltet aus."""

    def __init__(self, page: "FieldPage", f: Field, value: Any) -> None:
        kinds = [discord.ChannelType.voice] if f.kind == "voice" else [discord.ChannelType.text,
                                                                      discord.ChannelType.news]
        defaults = [discord.SelectDefaultValue(id=i, type=discord.SelectDefaultValueType.channel)
                    for i in ids_of(f, value)]
        super().__init__(channel_types=kinds, default_values=defaults, **limits(f))
        self.page, self.field = page, f

    async def callback(self, interaction: discord.Interaction) -> None:
        ids = [str(channel.id) for channel in self.values]
        await self.page.save(interaction, {self.field.key: chosen(self.field, ids)})


class FieldRoleSelect(discord.ui.RoleSelect["FieldPage"]):
    """Rolle oder Rollen, vorbelegt mit dem gespeicherten Wert; alles abwählen schaltet aus."""

    def __init__(self, page: "FieldPage", f: Field, value: Any) -> None:
        defaults = [discord.SelectDefaultValue(id=i, type=discord.SelectDefaultValueType.role)
                    for i in ids_of(f, value)]
        super().__init__(default_values=defaults, **limits(f))
        self.page, self.field = page, f

    async def callback(self, interaction: discord.Interaction) -> None:
        ids = [str(role.id) for role in self.values]
        await self.page.save(interaction, {self.field.key: chosen(self.field, ids)})


class FieldChoice(discord.ui.Select["FieldPage"]):
    def __init__(self, page: "FieldPage", f: Field, value: Any) -> None:
        options = [discord.SelectOption(label=label, value=v, default=v == value) for v, label in f.choices()]
        super().__init__(placeholder=f.label, options=options, custom_id=f"setup:{f.key}")
        self.page, self.field = page, f

    async def callback(self, interaction: discord.Interaction) -> None:
        value = self.values[0] if self.values else self.field.default
        await self.page.save(interaction, {self.field.key: value})


class FieldToggle(discord.ui.Button["FieldPage"]):
    def __init__(self, page: "FieldPage", f: Field, value: bool) -> None:
        style = discord.ButtonStyle.success if value else discord.ButtonStyle.secondary
        super().__init__(label=f"{f.label}: {'an' if value else 'aus'}", style=style, custom_id=f"setup:{f.key}")
        self.page, self.field, self.value = page, f, value

    async def callback(self, interaction: discord.Interaction) -> None:
        await self.page.save(interaction, {self.field.key: not self.value})


class EditValuesButton(discord.ui.Button["FieldPage"]):
    def __init__(self, page: "FieldPage", fields: list[Field]) -> None:
        super().__init__(label="Werte eingeben", emoji="✏️", style=discord.ButtonStyle.primary,
                         custom_id=f"setup:edit:{page_id(page.section, page.index)}")
        self.page, self.fields = page, fields[:MAX_MODAL_INPUTS]

    async def callback(self, interaction: discord.Interaction) -> None:
        await interaction.response.send_modal(ValuesModal(self.page, self.fields))


class BackButton(discord.ui.Button["FieldPage"]):
    def __init__(self, back: Back) -> None:
        super().__init__(label="Zurück", emoji="⬅️", style=discord.ButtonStyle.secondary, custom_id="setup:back",
                         row=4)
        self.back = back

    async def callback(self, interaction: discord.Interaction) -> None:
        await self.back(interaction)


def field_item(page: "FieldPage", f: Field, value: Any) -> discord.ui.Item["FieldPage"] | None:
    """Das Bedienelement für ein Feld; Zahlen und Texte gehen über EditValuesButton."""
    if f.kind in ("channel", "voice", "channels"):
        return FieldChannelSelect(page, f, value)
    if f.kind in ("role", "roles"):
        return FieldRoleSelect(page, f, value)
    if f.kind == "choice":
        return FieldChoice(page, f, value)
    if f.kind == "bool":
        return FieldToggle(page, f, bool(value))
    return None


class FieldPage(discord.ui.View):
    """Eine Seite des Panels: die Felder einer Gruppe, dazu `extras` und ein Zurück-Knopf."""

    def __init__(self, client: discord.Client, db: Database, guild: discord.Guild, section: Section, index: int,
                 back: Back, *, extras: tuple[discord.ui.Item[Any], ...] = (), persistent: bool = False) -> None:
        super().__init__(timeout=None if persistent else TIMEOUT_S)
        self.client, self.db, self.guild, self.section, self.index = client, db, guild, section, index
        self.back, self.extras, self.persistent = back, extras, persistent
        self.group, self.fields = section.groups()[index]
        for f in self.fields:
            item = field_item(self, f, read_field(db, guild.id, f))
            if item is not None:
                self.add_item(item)
        texts = [f for f in self.fields if f.kind in MODAL_KINDS]
        if texts:
            self.add_item(EditValuesButton(self, texts))
        for extra in extras:
            self.add_item(extra)
        self.add_item(BackButton(back))

    def embed(self) -> discord.Embed:
        lines = [f"{f.label}: {fmt_value(self.guild, f, read_field(self.db, self.guild.id, f))}" for f in self.fields]
        hints = [f"*{f.label}:* {f.hint}" for f in self.fields if f.hint]
        e = discord.Embed(title=page_title(self.section, self.group), description="\n".join(lines),
                          colour=discord.Colour.blurple())
        if hints:
            e.add_field(name="Hinweise", value="\n".join(hints)[:1024], inline=False)
        return e

    async def save(self, interaction: discord.Interaction, values: dict[str, Any]) -> None:
        try:
            await save_values(self.client, self.db, self.guild, self.section, values)
        except ApiError as e:
            await interaction.response.send_message(e.detail, ephemeral=True)
            return
        page = FieldPage(self.client, self.db, self.guild, self.section, self.index, self.back,
                         extras=self.extras, persistent=self.persistent)
        await interaction.response.edit_message(embed=page.embed(), view=page)


class ValuesModal(discord.ui.Modal):
    """Zahlen und Texte einer Seite in einem Formular; Zahlen werden vor dem Speichern geprüft."""

    def __init__(self, page: FieldPage, fields: list[Field]) -> None:
        super().__init__(title=page_title(page.section, page.group)[:45])
        self.page = page
        self.inputs: dict[str, tuple[Field, discord.ui.TextInput[Any]]] = {}
        for f in fields:
            current = read_field(page.db, page.guild.id, f)
            text_input: discord.ui.TextInput[Any] = discord.ui.TextInput(
                label=f.label[:45], default=str(current) if current not in (None, "") else None, required=False,
                style=discord.TextStyle.paragraph if f.kind == "textarea" else discord.TextStyle.short,
                placeholder=f.hint[:100] or None)
            self.inputs[f.key] = (f, text_input)
            self.add_item(text_input)

    async def on_submit(self, interaction: discord.Interaction) -> None:
        values: dict[str, Any] = {}
        for key, (f, text_input) in self.inputs.items():
            text = str(text_input.value).strip()
            if f.kind != "int":
                values[key] = text
            elif not text:
                values[key] = f.default  # leer: wieder der Standard, bei „0 = aus“ also aus
            elif text.lstrip("-").isdigit():
                values[key] = int(text)
            else:
                await interaction.response.send_message(f"{f.label}: bitte eine Zahl eingeben.", ephemeral=True)
                return
        await self.page.save(interaction, values)
