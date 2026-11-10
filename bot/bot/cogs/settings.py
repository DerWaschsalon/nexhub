"""/setup: Einstellungen des Bots pro Server. Nur für Leute mit „Server verwalten“.

Die einfachen Einstellungen (Kanäle, Rollen, Schalter, Zahlen, Texte) stehen als Schema in den Modulen
(`bot/modules/*/*/settings.py`, zusammengestellt in `bot/forms.py`). Daraus entstehen `/setup anzeigen`,
`/setup ändern` und das Klick-Panel (`bot/panel.py`). Hier steht nur, was über ein Schema hinausgeht:
Verifizierung einrichten, Temp-Voice-Kanal anlegen, AION-Token zeigen, Management-Kanal.
"""

from __future__ import annotations

import logging
import re
import secrets
from collections.abc import Callable
from typing import Any

import discord
from discord import app_commands
from discord.ext import commands

from ..core.confirm import Confirm
from ..errors import UserError
from ..forms import SECTIONS, Section, find_field, read_field, save_values
from ..hubpages import ApiError, Field
from ..panel import FieldPage, fmt_value, overview_embed, page_title

log = logging.getLogger(__name__)

DEFAULT_VERIFY_TEXT = (
    "Lies dir die Regeln hier im Kanal durch. Mit Klick auf **Regeln akzeptiert** bekommst du Zugriff "
    "auf den restlichen Server."
)
TIMEOUT_S = 180
MAX_CHOICES = 25  # Discord zeigt beim Tippen höchstens 25 Vorschläge
ON_WORDS = ("an", "ja", "true", "1", "on")
OFF_WORDS = ("aus", "nein", "false", "0", "off", "")
ID_PATTERN = re.compile(r"\d{15,20}")  # Discord-ID, auch aus <#…> oder <@&…>


# ---- Verifizierung: geteilte Logik zwischen `/setup verifizierung` und dem Klick-Panel ----


def verification_preview_embed(
    guild: discord.Guild, regel_kanal: discord.TextChannel, rolle: discord.Role | None
) -> discord.Embed:
    affected = sum(1 for m in guild.members if not m.bot and (not rolle or rolle not in m.roles))
    e = discord.Embed(title="🔒 Verifizierung einrichten?", colour=discord.Colour.orange())
    e.add_field(name="Regel-Kanal", value=regel_kanal.mention, inline=False)
    e.add_field(name="Rolle", value=rolle.mention if rolle else "neu: „Verifiziert“", inline=False)
    e.add_field(
        name="Was passiert",
        value=(f"• @everyone verliert „Kanäle ansehen“ serverweit\n"
               f"• {regel_kanal.mention} bleibt für alle sichtbar\n"
               f"• Die Verifiziert-Rolle bekommt „Kanäle ansehen“ automatisch zurück\n"
               f"• {affected} bestehende Mitglieder bekommen die Rolle sofort, damit niemand ausgesperrt wird\n"
               f"• Die Autorolle (falls gesetzt, z. B. „Neuling“) bekommen neue Mitglieder weiterhin sofort "
               "beim Beitritt, unabhängig von der Verifizierung"),
        inline=False,
    )
    return e


async def apply_verification(
    db, guild: discord.Guild, regel_kanal: discord.TextChannel, rolle: discord.Role | None,
    text: str | None, requested_by,
) -> discord.Role:
    me = guild.me
    if not (me.guild_permissions.manage_roles and me.guild_permissions.manage_channels):
        raise UserError("Mir fehlen die Rechte „Rollen verwalten“ und „Kanäle verwalten“.")
    if rolle and (rolle.managed or rolle >= me.top_role):
        raise UserError(f"{rolle.mention} kann ich nicht vergeben. Meine Rolle muss in den "
                        "Servereinstellungen über ihr stehen.")

    if rolle is None:
        rolle = await guild.create_role(name="Verifiziert", reason=f"Verifizierung durch {requested_by}")
    role_perms = rolle.permissions
    role_perms.update(view_channel=True)
    await rolle.edit(permissions=role_perms, reason="Verifizierung eingerichtet")

    for member in guild.members:
        if not member.bot and rolle not in member.roles:
            try:
                await member.add_roles(rolle, reason="Verifizierung eingerichtet – Bestandsmitglied")
            except discord.HTTPException as ex:
                log.warning("Verifizierung Bestandsrolle %s: %r", member.id, ex)

    await regel_kanal.set_permissions(
        guild.default_role, view_channel=True, reason="Verifizierung: Regel-Kanal bleibt sichtbar"
    )
    everyone_perms = guild.default_role.permissions
    everyone_perms.update(view_channel=False)
    await guild.default_role.edit(permissions=everyone_perms, reason=f"Verifizierung durch {requested_by}")

    await db.set(guild.id, "verify_role", rolle.id)
    await db.set(guild.id, "verify_channel", regel_kanal.id)
    await db.set(guild.id, "verify_active", True)

    panel_embed = discord.Embed(
        title="📜 Regeln", description=(text or DEFAULT_VERIFY_TEXT).replace("\\n", "\n"),
        colour=discord.Colour.blurple(),
    )
    panel_message = await regel_kanal.send(embed=panel_embed, view=VerifyPanelView())
    await db.set(guild.id, "verify_message", panel_message.id)
    return rolle


async def turn_off_verification(db, guild: discord.Guild, requested_by) -> None:
    everyone_perms = guild.default_role.permissions
    everyone_perms.update(view_channel=True)
    await guild.default_role.edit(permissions=everyone_perms, reason=f"Verifizierung aus durch {requested_by}")
    await db.set(guild.id, "verify_active", False)



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
        channel = await create_tempvoice_hub(interaction.guild)
        await self.panel.cog.db.set(interaction.guild_id, "tempvoice_hub", channel.id)
        await self.panel.open_page(interaction, SECTIONS["allgemein"], "Musik & Voice")


class AionTokenButton(discord.ui.Button[FieldPage]):
    def __init__(self, panel: "SettingsPanel") -> None:
        super().__init__(label="API-Token erzeugen/anzeigen", emoji="🔑", style=discord.ButtonStyle.secondary,
                         custom_id="setup:aion_token")
        self.panel = panel

    async def callback(self, interaction: discord.Interaction) -> None:
        db = self.panel.cog.db
        token = db.get(interaction.guild_id, "aion_api_token")
        if not token:
            token = secrets.token_urlsafe(24)
            await db.set(interaction.guild_id, "aion_api_token", token)
        aion_cog = self.panel.cog.bot.get_cog("AionDedup")
        await interaction.response.send_message(
            f"Im NexBoard unter Discord-Bot eintragen:\n`{aion_cog.api_url()}`\nToken: `{token}`\n\n"
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
                   action: Callable[[discord.Interaction], Any],
                   style: discord.ButtonStyle = discord.ButtonStyle.secondary) -> None:
        button: discord.ui.Button[Any] = discord.ui.Button(label=label[:80], emoji=emoji, style=style,
                                                           custom_id=custom_id or None)
        button.callback = action
        self.add_item(button)

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
        await interaction.response.edit_message(view=VerifyView(self))

    async def open_notifications(self, interaction: discord.Interaction) -> None:
        from .notifications import NotificationsHomeView, home_embed

        notif_cog = self.cog.bot.get_cog("Notifications")
        await interaction.response.edit_message(
            embed=home_embed(), view=NotificationsHomeView(notif_cog, self.guild, self.persistent)
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

class VerifySetupChannelSelect(discord.ui.ChannelSelect):
    def __init__(self, panel: "SettingsPanel"):
        super().__init__(placeholder="Regel-Kanal wählen …", channel_types=[discord.ChannelType.text], row=0,
                         custom_id="setup:select:verify_setup_channel")
        self.panel = panel

    async def callback(self, interaction: discord.Interaction):
        channel = interaction.guild.get_channel(self.values[0].id) or self.values[0]
        await interaction.response.edit_message(view=VerifySetupRoleView(self.panel, channel))


class VerifySetupRoleSelect(discord.ui.RoleSelect):
    def __init__(self, panel: "SettingsPanel", channel: discord.TextChannel):
        super().__init__(placeholder="Vorhandene Rolle für Verifizierte wählen …", row=0,
                         custom_id="setup:select:verify_setup_role")
        self.panel = panel
        self.channel = channel

    async def callback(self, interaction: discord.Interaction):
        await start_verification_confirm(interaction, self.panel, self.channel, self.values[0])


class VerifySetupNewRoleButton(discord.ui.Button):
    def __init__(self, panel: "SettingsPanel", channel: discord.TextChannel):
        super().__init__(label="Stattdessen neue Rolle „Verifiziert“ anlegen", style=discord.ButtonStyle.secondary,
                         row=1, custom_id="setup:verify_setup_new_role")
        self.panel = panel
        self.channel = channel

    async def callback(self, interaction: discord.Interaction):
        await start_verification_confirm(interaction, self.panel, self.channel, None)


class VerifySetupRoleView(discord.ui.View):
    def __init__(self, panel: "SettingsPanel", channel: discord.TextChannel):
        super().__init__(timeout=None if panel.persistent else 180)
        self.add_item(VerifySetupRoleSelect(panel, channel))
        self.add_item(VerifySetupNewRoleButton(panel, channel))
        self.add_item(BackButton(panel))


class VerifySetupStartButton(discord.ui.Button):
    def __init__(self, panel: "SettingsPanel"):
        super().__init__(label="Einrichten starten", emoji="🔒", style=discord.ButtonStyle.success, row=0,
                         custom_id="setup:verify_setup_start")
        self.panel = panel

    async def callback(self, interaction: discord.Interaction):
        me = interaction.guild.me
        if not (me.guild_permissions.manage_roles and me.guild_permissions.manage_channels):
            return await interaction.response.send_message(
                "Mir fehlen die Rechte „Rollen verwalten“ und „Kanäle verwalten“.", ephemeral=True,
            )
        view = discord.ui.View(timeout=None if self.panel.persistent else 180)
        view.add_item(VerifySetupChannelSelect(self.panel))
        view.add_item(BackButton(self.panel))
        await interaction.response.edit_message(view=view)


async def start_verification_confirm(
    interaction: discord.Interaction, panel: "SettingsPanel", channel: discord.TextChannel, rolle: discord.Role | None
) -> None:
    if rolle and (rolle.managed or rolle >= interaction.guild.me.top_role):
        return await interaction.response.send_message(
            f"{rolle.mention} kann ich nicht vergeben. Meine Rolle muss in den Servereinstellungen über ihr stehen.",
            ephemeral=True,
        )
    e = verification_preview_embed(interaction.guild, channel, rolle)
    confirm = Confirm(interaction.user.id, "Einrichten")
    await interaction.response.edit_message(embed=e, view=confirm)
    await confirm.wait()
    if not confirm.confirmed:
        return
    await apply_verification(panel.cog.db, interaction.guild, channel, rolle, None, interaction.user)
    await interaction.edit_original_response(
        content=f"✅ Verifizierung eingerichtet. Panel steht in {channel.mention}.",
        embed=panel.embed(), view=panel,
    )


class VerifyTextModal(discord.ui.Modal, title="Regeln-Text"):
    def __init__(self, panel: "SettingsPanel", current: str):
        super().__init__()
        self.panel = panel
        self.text = discord.ui.TextInput(
            label="Regeln-Text", style=discord.TextStyle.paragraph, default=current, max_length=1000,
        )
        self.add_item(self.text)

    async def on_submit(self, interaction: discord.Interaction):
        db = self.panel.cog.db
        channel_id = db.get_int(interaction.guild_id, "verify_channel")
        message_id = db.get_int(interaction.guild_id, "verify_message")
        channel = interaction.guild.get_channel(channel_id) if channel_id else None
        if not channel or not message_id:
            return await interaction.response.send_message("Verifizierung ist nicht mehr eingerichtet.", ephemeral=True)
        try:
            message = await channel.fetch_message(message_id)
        except discord.NotFound:
            return await interaction.response.send_message(
                "Das Regeln-Panel wurde gelöscht. Einmal neu einrichten.", ephemeral=True
            )
        embed = message.embeds[0] if message.embeds else discord.Embed(title="📜 Regeln", colour=discord.Colour.blurple())
        embed.description = str(self.text.value).replace("\\n", "\n")
        await message.edit(embed=embed)
        await interaction.response.edit_message(embed=self.panel.embed(), view=VerifyView(self.panel))


class VerifyTextButton(discord.ui.Button):
    def __init__(self, panel: "SettingsPanel"):
        super().__init__(label="Text ändern", emoji="✏️", style=discord.ButtonStyle.secondary, row=0,
                         custom_id="setup:verify_text_btn")
        self.panel = panel

    async def callback(self, interaction: discord.Interaction):
        db = self.panel.cog.db
        channel_id = db.get_int(interaction.guild_id, "verify_channel")
        message_id = db.get_int(interaction.guild_id, "verify_message")
        current = DEFAULT_VERIFY_TEXT
        channel = interaction.guild.get_channel(channel_id) if channel_id else None
        if channel and message_id:
            try:
                message = await channel.fetch_message(message_id)
                if message.embeds and message.embeds[0].description:
                    current = message.embeds[0].description
            except discord.NotFound:
                pass
        await interaction.response.send_modal(VerifyTextModal(self.panel, current))


class VerifyOffButton(discord.ui.Button):
    def __init__(self, panel: "SettingsPanel"):
        super().__init__(label="Ausschalten", emoji="🔓", style=discord.ButtonStyle.danger, row=0,
                         custom_id="setup:verify_off")
        self.panel = panel

    async def callback(self, interaction: discord.Interaction):
        await turn_off_verification(self.panel.cog.db, interaction.guild, interaction.user)
        await interaction.response.edit_message(embed=self.panel.embed(), view=VerifyView(self.panel))


class VerifyView(discord.ui.View):
    def __init__(self, panel: "SettingsPanel"):
        super().__init__(timeout=None if panel.persistent else 180)
        self.add_item(VerifyTextButton(panel) if panel.cog.db.get_bool(panel.guild.id, "verify_active")
                     else VerifySetupStartButton(panel))
        if panel.cog.db.get_bool(panel.guild.id, "verify_active"):
            self.add_item(VerifyOffButton(panel))
        self.add_item(BackButton(panel))


class VerifyPanelView(discord.ui.View):
    """Persistent über `custom_id` – wird im `on_interaction`-Listener unten behandelt, nicht hier."""

    def __init__(self):
        super().__init__(timeout=None)
        self.add_item(discord.ui.Button(
            label="Regeln akzeptiert", emoji="✅", style=discord.ButtonStyle.success, custom_id="verify:accept",
        ))



@app_commands.guild_only()
@app_commands.default_permissions(manage_guild=True)
class Setup(commands.GroupCog, group_name="setup", group_description="Einstellungen des Bots"):
    def __init__(self, bot: commands.Bot) -> None:
        self.bot = bot
        self.db = bot.db  # type: ignore[attr-defined]

    @app_commands.command(name="anzeigen", description="Alle Einstellungen anzeigen")
    async def show(self, interaction: discord.Interaction) -> None:
        await interaction.response.send_message(embed=overview_embed(self.db, interaction.guild), ephemeral=True)

    @app_commands.command(name="panel", description="Einstellungen bequem per Klick ändern, ohne Befehle zu tippen")
    async def panel(self, interaction: discord.Interaction) -> None:
        view = SettingsPanel(self, interaction.guild)
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
        try:
            await save_values(self.bot, self.db, interaction.guild, section, {f.key: parse_input(f, wert)})
        except ApiError as e:
            raise UserError(e.detail) from None
        value = read_field(self.db, interaction.guild_id, f)
        await interaction.response.send_message(f"**{f.label}:** {fmt_value(interaction.guild, f, value)}",
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
    ):
        guild = interaction.guild
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
    ):
        if aus:
            await self.db.set(interaction.guild_id, "tempvoice_hub", None)
            return await interaction.response.send_message("Temp-Voice ist aus.", ephemeral=True)
        if kanal is None:
            kanal = await create_tempvoice_hub(interaction.guild)
        await self.db.set(interaction.guild_id, "tempvoice_hub", kanal.id)
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
    ):
        guild = interaction.guild
        me = guild.me

        if aus:
            if not self.db.get_bool(guild.id, "verify_active"):
                return await interaction.response.send_message("Verifizierung ist schon aus.", ephemeral=True)
            await turn_off_verification(self.db, guild, interaction.user)
            return await interaction.response.send_message(
                "Verifizierung ist aus, alle sehen den Server wieder wie vorher. Die Rolle selbst habe ich "
                "nicht gelöscht, das kannst du bei Bedarf in den Servereinstellungen tun.", ephemeral=True,
            )

        if not regel_kanal:
            raise UserError("Gib einen Regel-Kanal an (`regel_kanal:`).")
        if not (me.guild_permissions.manage_roles and me.guild_permissions.manage_channels):
            raise UserError("Mir fehlen die Rechte „Rollen verwalten“ und „Kanäle verwalten“.")
        if rolle and (rolle.managed or rolle >= me.top_role):
            raise UserError(f"{rolle.mention} kann ich nicht vergeben. Meine Rolle muss in den "
                            "Servereinstellungen über ihr stehen.")

        e = verification_preview_embed(guild, regel_kanal, rolle)
        view = Confirm(interaction.user.id, "Einrichten")
        await interaction.response.send_message(embed=e, view=view, ephemeral=True)
        await view.wait()
        if not view.confirmed:
            return

        await apply_verification(self.db, guild, regel_kanal, rolle, text, interaction.user)
        await interaction.edit_original_response(
            content=f"✅ Verifizierung eingerichtet. Panel steht in {regel_kanal.mention}.", embed=None, view=None
        )

    @app_commands.command(name="regeln-text", description="Text im Regeln-Panel ändern (Verifizierung muss schon eingerichtet sein)")
    @app_commands.describe(text="Neuer Text im Regeln-Panel")
    async def rules_text(self, interaction: discord.Interaction, text: str):
        channel_id = self.db.get_int(interaction.guild_id, "verify_channel")
        message_id = self.db.get_int(interaction.guild_id, "verify_message")
        channel = interaction.guild.get_channel(channel_id) if channel_id else None
        if not channel or not message_id:
            raise UserError("Noch keine Verifizierung eingerichtet: `/setup verifizierung`.")
        try:
            message = await channel.fetch_message(message_id)
        except discord.NotFound:
            raise UserError("Das Regeln-Panel wurde gelöscht. Einmal neu einrichten: `/setup verifizierung`.")
        embed = message.embeds[0] if message.embeds else discord.Embed(title="📜 Regeln", colour=discord.Colour.blurple())
        embed.description = text.replace("\\n", "\n")
        await message.edit(embed=embed)
        await interaction.response.send_message(f"Regeln-Text in {channel.mention} aktualisiert.", ephemeral=True)

    @commands.Cog.listener()
    async def on_interaction(self, interaction: discord.Interaction):
        if interaction.type is not discord.InteractionType.component:
            return
        if (interaction.data or {}).get("custom_id") != "verify:accept" or not interaction.guild:
            return
        guild = interaction.guild
        role_id = self.db.get_int(guild.id, "verify_role")
        role = guild.get_role(role_id) if role_id else None
        if not role:
            return await interaction.response.send_message("Verifizierung ist nicht mehr eingerichtet.", ephemeral=True)
        member = interaction.user
        if role in member.roles:
            return await interaction.response.send_message("Du bist schon verifiziert.", ephemeral=True)
        try:
            await member.add_roles(role, reason="Verifizierung bestätigt")
        except discord.HTTPException:
            return await interaction.response.send_message(
                "Das hat nicht geklappt, sag einem Admin Bescheid.", ephemeral=True
            )
        autorole_id = self.db.get_int(guild.id, "autorole")
        if autorole_id:
            autorole = guild.get_role(autorole_id)
            if autorole and not autorole.managed and autorole < guild.me.top_role and autorole not in member.roles:
                try:
                    await member.add_roles(autorole, reason="Verifizierung bestätigt – Autorolle")
                except discord.HTTPException as ex:
                    log.warning("Autorolle nach Verifizierung %s: %r", member.id, ex)
        await interaction.response.send_message("✅ Verifiziert! Viel Spaß auf dem Server.", ephemeral=True)


async def setup(bot: commands.Bot) -> None:
    await bot.add_cog(Setup(bot))
