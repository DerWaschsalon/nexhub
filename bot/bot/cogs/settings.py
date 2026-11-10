"""/setup: Einstellungen des Bots pro Server. Nur für Leute mit „Server verwalten“.

Die einfachen Einstellungen (Kanäle, Rollen, Schalter, Zahlen, Texte) stehen als Schema in den Modulen
(`bot/modules/*/*/settings.py`, zusammengestellt in `bot/forms.py`). Daraus entstehen `/setup anzeigen`,
`/setup ändern` und das Klick-Panel (`bot/panel.py`). Hier steht nur, was über ein Schema hinausgeht:
Verifizierung einrichten, Temp-Voice-Kanal anlegen, AION-Token zeigen, Management-Kanal.
"""

from __future__ import annotations

import logging
import re
from collections.abc import Callable
from typing import TYPE_CHECKING, Any, TypeVar

import discord
from discord import app_commands
from discord.ext import commands

from ..core import BotModule
from ..core.buttons import ActionButton, ClickHandler
from ..core.confirm import Confirm
from ..errors import UserError
from ..forms import SECTIONS, Section, find_field, read_field, save_values
from ..hubpages import ApiError, Field
from ..modules.aion2.runs import RunPosts
from ..modules.notify.feeds import NotificationFeeds
from ..modules.server.verification import Verification, check_setup_rights, preview_embed
from ..panel import FieldPage, fmt_value, overview_embed, page_title

if TYPE_CHECKING:
    from ..__main__ import Bot

log = logging.getLogger(__name__)
M = TypeVar("M", bound=BotModule)

TIMEOUT_S = 180
MAX_CHOICES = 25  # Discord zeigt beim Tippen höchstens 25 Vorschläge
ON_WORDS = ("an", "ja", "true", "1", "on")
OFF_WORDS = ("aus", "nein", "false", "0", "off", "")
ID_PATTERN = re.compile(r"\d{15,20}")  # Discord-ID, auch aus <#…> oder <@&…>


# ---- Panel: Hauptmenü aus den Schemas, Sonderknöpfe für einzelne Seiten -----------------


class BackButton(discord.ui.Button["SettingsPanel"]):
    def __init__(self, panel: "SettingsPanel") -> None:
        super().__init__(label="Zurück", emoji="⬅️", style=discord.ButtonStyle.secondary, row=4,
                         custom_id="setup:back")
        self.panel = panel

    async def callback(self, interaction: discord.Interaction) -> None:
        await self.panel.show(interaction)


class TempVoiceCreateButton(discord.ui.Button[FieldPage]):
    def __init__(self, panel: "SettingsPanel") -> None:
        super().__init__(label="Neuen Temp-Voice-Kanal anlegen", emoji="➕", style=discord.ButtonStyle.secondary,
                         custom_id="setup:tempvoice_create")
        self.panel = panel

    async def callback(self, interaction: discord.Interaction) -> None:
        channel = await create_tempvoice_hub(self.panel.guild)
        await self.panel.cog.db.set(self.panel.guild.id, "tempvoice_hub", channel.id)
        await self.panel.open_page(interaction, SECTIONS["allgemein"], "Musik & Voice")


class AionTokenButton(discord.ui.Button[FieldPage]):
    def __init__(self, panel: "SettingsPanel") -> None:
        super().__init__(label="API-Token erzeugen/anzeigen", emoji="🔑", style=discord.ButtonStyle.secondary,
                         custom_id="setup:aion_token")
        self.panel = panel

    async def callback(self, interaction: discord.Interaction) -> None:
        runs = self.panel.cog.module("aion2.runs", RunPosts)
        token = await runs.token(self.panel.guild.id)
        await interaction.response.send_message(
            f"Im NexBoard unter Discord-Bot eintragen:\n`{runs.api_url()}`\nToken: `{token}`\n\n"
            "Geheim halten. Für einen neuen Token (macht den alten ungültig): `/aion token:True`.",
            ephemeral=True,
        )


# Sonderknöpfe je Seite (Bereich, Gruppe): was über ein Schema hinausgeht
EXTRAS: dict[tuple[str, str], Callable[["SettingsPanel"], discord.ui.Item[Any]]] = {
    ("allgemein", "Musik & Voice"): TempVoiceCreateButton,
    ("aion", ""): AionTokenButton,
}


class SettingsPanel(discord.ui.View):
    """Hauptmenü: ein Knopf je Seite aus forms.SECTIONS, dazu Verifizierung und Benachrichtigungen.
    `persistent=True`: fest in einem Kanal gepostet, überlebt Neustarts (`Setup.register_persistent_views`);
    sonst ephemere Antwort auf `/setup panel`."""

    def __init__(self, cog: "Setup", guild: discord.Guild, *, persistent: bool = False) -> None:
        super().__init__(timeout=None if persistent else TIMEOUT_S)
        self.cog = cog
        self.guild = guild
        self.persistent = persistent
        for section in SECTIONS.values():
            for index, (group, _fields) in enumerate(section.groups()):
                self.add_page_button(section, index, group)
        self.add_button("Verifizierung", "🔒", "setup:open:verify", self.open_verify)
        self.add_button("Benachrichtigungen", "🔔", "setup:open:notifications", self.open_notifications)
        if not persistent:
            self.add_button("Schließen", "✖️", "", self.close, style=discord.ButtonStyle.danger)

    def add_button(self, label: str, emoji: str | None, custom_id: str,
                   action: ClickHandler,
                   style: discord.ButtonStyle = discord.ButtonStyle.secondary) -> None:
        self.add_item(ActionButton(action, label=label[:80], emoji=emoji, style=style, custom_id=custom_id or None))

    def add_page_button(self, section: Section, index: int, group: str) -> None:
        async def open_it(interaction: discord.Interaction) -> None:
            await self.open_page(interaction, section, group)

        self.add_button(page_title(section, group), None, f"setup:open:{section.id}:{index}", open_it)

    def embed(self) -> discord.Embed:
        return overview_embed(self.cog.db, self.guild)

    async def show(self, interaction: discord.Interaction) -> None:
        await interaction.response.edit_message(content=None, embed=self.embed(), view=self)

    async def open_page(self, interaction: discord.Interaction, section: Section, group: str) -> None:
        index = [name for name, _fields in section.groups()].index(group)
        extra = EXTRAS.get((section.id, group))
        page = FieldPage(self.cog.bot, self.cog.db, self.guild, section, index, self.show,
                         extras=(extra(self),) if extra else (), persistent=self.persistent)
        await interaction.response.edit_message(embed=page.embed(), view=page)

    async def open_verify(self, interaction: discord.Interaction) -> None:
        from ..modules.server.verification.panel import Flow

        await Flow(self.cog.verify_module(), self.guild, self.persistent, self.show).show(interaction)

    async def open_notifications(self, interaction: discord.Interaction) -> None:
        from ..modules.notify.feeds.wizard import NotificationsHomeView, home_embed

        feeds = self.cog.module("notify.feeds", NotificationFeeds)
        await interaction.response.edit_message(
            embed=home_embed(), view=NotificationsHomeView(feeds, self.guild, self.persistent)
        )

    async def close(self, interaction: discord.Interaction) -> None:
        await interaction.response.edit_message(content="Einstellungen geschlossen.", embed=None, view=None)


async def create_tempvoice_hub(guild: discord.Guild) -> discord.VoiceChannel:
    if not guild.me.guild_permissions.manage_channels:
        raise UserError("Mir fehlt das Recht „Kanäle verwalten“.")
    category = await guild.create_category("Sprachkanäle")
    return await guild.create_voice_channel("➕ Kanal erstellen", category=category)


def parse_input(f: Field, text: str) -> Any:
    """Eingabe aus `/setup ändern` in die Form, die forms.save_values erwartet."""
    text = text.strip()
    if f.kind in ("channel", "voice", "role"):
        found = ID_PATTERN.search(text)
        if text and not found:
            raise UserError(f"{f.label}: bitte als Erwähnung oder ID angeben, leer schaltet aus.")
        return found.group() if found else None
    if f.kind in ("channels", "roles"):
        return ID_PATTERN.findall(text)
    if f.kind == "bool":
        if text.lower() not in ON_WORDS + OFF_WORDS:
            raise UserError(f"{f.label}: bitte „an“ oder „aus“.")
        return text.lower() in ON_WORDS
    if f.kind == "int":
        if not text:
            return f.default
        if not text.lstrip("-").isdigit():
            raise UserError(f"{f.label}: bitte eine Zahl.")
        return int(text)
    return text


@app_commands.guild_only()
@app_commands.default_permissions(manage_guild=True)
class Setup(commands.GroupCog, group_name="setup", group_description="Einstellungen des Bots"):
    def __init__(self, bot: Bot) -> None:
        self.bot = bot
        self.db = bot.db

    def module(self, module_id: str, kind: type[M]) -> M:
        """Ein Modul des Bots mit seinem genauen Typ (für Token, Assistenten und Verifizierung)."""
        module = self.bot.modules.module(module_id)
        assert isinstance(module, kind)
        return module

    def verify_module(self) -> Verification:
        return self.module("server.verification", Verification)

    @staticmethod
    def guild_of(interaction: discord.Interaction) -> discord.Guild:
        if interaction.guild is None:  # alle /setup-Befehle sind guild_only
            raise UserError("Das geht nur auf einem Server.")
        return interaction.guild

    @app_commands.command(name="anzeigen", description="Alle Einstellungen anzeigen")
    async def show(self, interaction: discord.Interaction) -> None:
        guild = self.guild_of(interaction)
        await interaction.response.send_message(embed=overview_embed(self.db, guild), ephemeral=True)

    @app_commands.command(name="panel", description="Einstellungen bequem per Klick ändern, ohne Befehle zu tippen")
    async def panel(self, interaction: discord.Interaction) -> None:
        view = SettingsPanel(self, self.guild_of(interaction))
        await interaction.response.send_message(embed=view.embed(), view=view, ephemeral=True)

    @app_commands.command(name="aendern", description="Eine Einstellung ändern: Kanal, Rolle, Zahl, Text oder an/aus")
    @app_commands.describe(
        einstellung="Welche Einstellung (Vorschläge beim Tippen)",
        wert="#Kanal, @Rolle, Zahl, Text oder an/aus; leer lassen schaltet aus",
    )
    async def change(self, interaction: discord.Interaction, einstellung: str, wert: str = "") -> None:
        found = find_field(einstellung)
        if found is None:
            raise UserError(f"Die Einstellung „{einstellung}“ gibt es nicht. Bitte aus den Vorschlägen wählen.")
        section, f = found
        guild = self.guild_of(interaction)
        try:
            await save_values(self.bot, self.db, guild, section, {f.key: parse_input(f, wert)})
        except ApiError as e:
            raise UserError(e.detail) from None
        value = read_field(self.db, guild.id, f)
        await interaction.response.send_message(f"**{f.label}:** {fmt_value(guild, f, value)}",
                                                ephemeral=True)

    @change.autocomplete("einstellung")
    async def change_autocomplete(
        self, interaction: discord.Interaction, current: str,
    ) -> list[app_commands.Choice[str]]:
        typed = current.lower()
        choices = []
        for section in SECTIONS.values():
            for f in section.fields:
                name = f"{section.title} · {f.label}"
                if typed in name.lower() or typed in f.key:
                    choices.append(app_commands.Choice(name=name[:100], value=f.key))
        return choices[:MAX_CHOICES]

    @app_commands.command(
        name="management-kanal",
        description="Festen Kanal mit dem Klick-Panel anlegen, z. B. unter einer Admin-Kategorie",
    )
    @app_commands.describe(
        kategorie="Kategorie, unter der der Kanal entsteht (übernimmt deren Sichtbarkeit, z. B. nur fürs Team)",
        neu="Vorhandenen Management-Kanal ersetzen, falls schon einer eingerichtet ist",
    )
    async def management_channel(
        self, interaction: discord.Interaction, kategorie: discord.CategoryChannel, neu: bool = False
    ) -> None:
        guild = self.guild_of(interaction)
        if not guild.me.guild_permissions.manage_channels:
            raise UserError("Mir fehlt das Recht „Kanäle verwalten“.")
        existing_id = self.db.get_int(guild.id, "mgmt_channel")
        if existing_id and not neu:
            existing = guild.get_channel(existing_id)
            if existing:
                raise UserError(f"Es gibt schon einen Management-Kanal: {existing.mention}. "
                                "Mit `neu:True` lege ich einen neuen an.")
        channel = await guild.create_text_channel(
            "bot-einstellungen", category=kategorie, reason=f"Management-Kanal eingerichtet durch {interaction.user}"
        )
        view = SettingsPanel(self, guild, persistent=True)
        message = await channel.send(embed=view.embed(), view=view)
        self.bot.add_view(view, message_id=message.id)
        await self.db.set(guild.id, "mgmt_channel", channel.id)
        await self.db.set(guild.id, "mgmt_message", message.id)
        await interaction.response.send_message(
            f"Fertig: {channel.mention} unter {kategorie.mention} angelegt. Das Panel dort bleibt dauerhaft "
            "klickbar, auch nach einem Neustart.", ephemeral=True
        )

    async def register_persistent_views(self) -> None:
        """Bei jedem Start: Management-Panels wieder anklickbar machen (siehe `management-kanal`)."""
        for guild_id in self.db.guilds_with("mgmt_message"):
            guild = self.bot.get_guild(guild_id)
            message_id = self.db.get_int(guild_id, "mgmt_message")
            if guild and message_id:
                self.bot.add_view(SettingsPanel(self, guild, persistent=True), message_id=message_id)

    @app_commands.command(name="temp-voice", description="„Join to create“-Kanal anlegen oder festlegen")
    @app_commands.describe(kanal="Vorhandener Sprachkanal; leer lassen = neuen anlegen", aus="Funktion abschalten")
    async def tempvoice(
        self, interaction: discord.Interaction, kanal: discord.VoiceChannel | None = None, aus: bool = False
    ) -> None:
        guild = self.guild_of(interaction)
        if aus:
            await self.db.set(guild.id, "tempvoice_hub", None)
            await interaction.response.send_message("Temp-Voice ist aus.", ephemeral=True)
            return
        if kanal is None:
            kanal = await create_tempvoice_hub(guild)
        await self.db.set(guild.id, "tempvoice_hub", kanal.id)
        await interaction.response.send_message(
            f"Wer {kanal.mention} betritt, bekommt einen eigenen Sprachkanal in derselben Kategorie.", ephemeral=True
        )

    @app_commands.command(
        name="verifizierung",
        description="Regeln-Panel: Mitglieder sehen den Server erst nach Bestätigen (mit Vorschau)",
    )
    @app_commands.describe(
        regel_kanal="Kanal mit den Regeln, bleibt für alle sichtbar, auch unverifiziert",
        rolle="Rolle für Verifizierte; leer lassen = neue Rolle „Verifiziert“ anlegen",
        text="Text im Panel (leer lassen = Standardtext)",
        aus="Verifizierung wieder abschalten – alle sehen den Server wieder wie vorher",
    )
    async def verification(
        self, interaction: discord.Interaction, regel_kanal: discord.TextChannel | None = None,
        rolle: discord.Role | None = None, text: str | None = None, aus: bool = False,
    ) -> None:
        guild = self.guild_of(interaction)
        module = self.verify_module()
        if aus:
            if not module.is_active(guild.id):
                raise UserError("Verifizierung ist schon aus.")
            await module.turn_off(guild, str(interaction.user))
            await interaction.response.send_message(
                "Verifizierung ist aus, alle sehen den Server wieder wie vorher. Die Rolle selbst habe ich "
                "nicht gelöscht, das kannst du bei Bedarf in den Servereinstellungen tun.", ephemeral=True,
            )
            return
        if not regel_kanal:
            raise UserError("Gib einen Regel-Kanal an (`regel_kanal:`).")
        check_setup_rights(guild, rolle)

        view = Confirm(interaction.user.id, "Einrichten")
        await interaction.response.send_message(embed=preview_embed(guild, regel_kanal, rolle), view=view,
                                                ephemeral=True)
        await view.wait()
        if not view.confirmed:
            return
        await module.apply(guild, regel_kanal, rolle, text, str(interaction.user))
        await interaction.edit_original_response(
            content=f"✅ Verifizierung eingerichtet. Panel steht in {regel_kanal.mention}.", embed=None, view=None
        )

    @app_commands.command(name="regeln-text",
                          description="Text im Regeln-Panel ändern (Verifizierung muss schon eingerichtet sein)")
    @app_commands.describe(text="Neuer Text im Regeln-Panel")
    async def rules_text(self, interaction: discord.Interaction, text: str) -> None:
        channel = await self.verify_module().set_text(self.guild_of(interaction), text)
        await interaction.response.send_message(f"Regeln-Text in {channel.mention} aktualisiert.", ephemeral=True)


async def setup(bot: Bot) -> None:
    await bot.add_cog(Setup(bot))
