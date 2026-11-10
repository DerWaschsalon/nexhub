"""Verifizierung im Klick-Panel von /setup: einrichten (Kanal, Rolle, Vorschau), Text ändern, ausschalten.

Kennt das Einstellungs-Panel nicht: „Zurück“ ruft die übergebene Funktion `back` auf.
"""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from typing import TYPE_CHECKING, Any

import discord

from bot.core.buttons import ActionButton
from bot.core.confirm import Confirm
from bot.errors import UserError

from . import DEFAULT_TEXT, check_setup_rights, preview_embed

if TYPE_CHECKING:
    from . import Verification

TIMEOUT_S = 180
Back = Callable[[discord.Interaction], Awaitable[None]]


class Flow:
    """Was alle Schritte brauchen: Modul, Server, ob das Panel fest gepostet ist, und der Weg zurück."""

    def __init__(self, module: Verification, guild: discord.Guild, persistent: bool, back: Back) -> None:
        self.module = module
        self.guild = guild
        self.persistent = persistent
        self.back = back

    def view(self) -> discord.ui.View:
        return discord.ui.View(timeout=None if self.persistent else TIMEOUT_S)

    def back_button(self) -> ActionButton:
        return ActionButton(self.back, label="Zurück", emoji="⬅️", style=discord.ButtonStyle.secondary, row=4,
                            custom_id="setup:back")

    def status_embed(self) -> discord.Embed:
        settings = self.module.settings.get(self.guild.id)
        e = discord.Embed(title="🔒 Verifizierung", colour=discord.Colour.blurple())
        if not settings.verify_active:
            e.description = "Aus. Alle sehen den ganzen Server."
            return e
        channel = self.module.rules_channel(self.guild)
        role = self.guild.get_role(settings.verify_role or 0)
        e.description = "An. Neue Mitglieder sehen den Server erst nach „Regeln akzeptiert“."
        e.add_field(name="Regel-Kanal", value=channel.mention if channel else "–")
        e.add_field(name="Rolle", value=role.mention if role else "–")
        return e

    def menu(self) -> discord.ui.View:
        view = self.view()
        if self.module.is_active(self.guild.id):
            view.add_item(ActionButton(self.open_text, label="Text ändern", emoji="✏️", row=0,
                                       custom_id="setup:verify_text_btn"))
            view.add_item(ActionButton(self.turn_off, label="Ausschalten", emoji="🔓", row=0,
                                       style=discord.ButtonStyle.danger, custom_id="setup:verify_off"))
        else:
            view.add_item(ActionButton(self.start, label="Einrichten starten", emoji="🔒", row=0,
                                       style=discord.ButtonStyle.success, custom_id="setup:verify_setup_start"))
        view.add_item(self.back_button())
        return view

    async def show(self, interaction: discord.Interaction, content: str | None = None) -> None:
        await interaction.response.edit_message(content=content, embed=self.status_embed(), view=self.menu())

    # ---- Einrichten: Kanal → Rolle → Vorschau --------------------------------------------------

    async def start(self, interaction: discord.Interaction) -> None:
        try:
            check_setup_rights(self.guild, None)
        except UserError as e:
            await interaction.response.send_message(str(e), ephemeral=True)
            return
        view = self.view()
        view.add_item(RulesChannelSelect(self))
        view.add_item(self.back_button())
        await interaction.response.edit_message(view=view)

    async def choose_role(self, interaction: discord.Interaction, channel: discord.TextChannel) -> None:
        async def new_role(inner: discord.Interaction) -> None:
            await self.confirm(inner, channel, None)

        view = self.view()
        view.add_item(VerifiedRoleSelect(self, channel))
        view.add_item(ActionButton(new_role, label="Stattdessen neue Rolle „Verifiziert“ anlegen", row=1,
                                   custom_id="setup:verify_setup_new_role"))
        view.add_item(self.back_button())
        await interaction.response.edit_message(view=view)

    async def confirm(self, interaction: discord.Interaction, channel: discord.TextChannel,
                      role: discord.Role | None) -> None:
        try:
            check_setup_rights(self.guild, role)
        except UserError as e:
            await interaction.response.send_message(str(e), ephemeral=True)
            return
        confirm = Confirm(interaction.user.id, "Einrichten")
        await interaction.response.edit_message(embed=preview_embed(self.guild, channel, role), view=confirm)
        await confirm.wait()
        if not confirm.confirmed:
            return
        await self.module.apply(self.guild, channel, role, None, str(interaction.user))
        await interaction.edit_original_response(
            content=f"✅ Verifizierung eingerichtet. Panel steht in {channel.mention}.",
            embed=self.status_embed(), view=self.menu())

    # ---- Eingerichtet: Text ändern, ausschalten --------------------------------------------------

    async def open_text(self, interaction: discord.Interaction) -> None:
        current = await self.module.current_text(self.guild) or DEFAULT_TEXT
        await interaction.response.send_modal(RulesTextModal(self, current))

    async def turn_off(self, interaction: discord.Interaction) -> None:
        await self.module.turn_off(self.guild, str(interaction.user))
        await self.show(interaction)


class RulesChannelSelect(discord.ui.ChannelSelect[discord.ui.View]):
    def __init__(self, flow: Flow) -> None:
        super().__init__(placeholder="Regel-Kanal wählen …", channel_types=[discord.ChannelType.text], row=0,
                         custom_id="setup:select:verify_setup_channel")
        self.flow = flow

    async def callback(self, interaction: discord.Interaction) -> None:
        # Die Auswahl liefert nur ein leichtes Kanal-Objekt; der echte Kanal kommt aus dem Cache
        channel = self.flow.guild.get_channel(self.values[0].id)
        if not isinstance(channel, discord.TextChannel):
            await interaction.response.send_message("Den Kanal finde ich nicht.", ephemeral=True)
            return
        await self.flow.choose_role(interaction, channel)


class VerifiedRoleSelect(discord.ui.RoleSelect[discord.ui.View]):
    def __init__(self, flow: Flow, channel: discord.TextChannel) -> None:
        super().__init__(placeholder="Vorhandene Rolle für Verifizierte wählen …", row=0,
                         custom_id="setup:select:verify_setup_role")
        self.flow = flow
        self.channel = channel

    async def callback(self, interaction: discord.Interaction) -> None:
        await self.flow.confirm(interaction, self.channel, self.values[0])


class RulesTextModal(discord.ui.Modal, title="Regeln-Text"):
    def __init__(self, flow: Flow, current: str) -> None:
        super().__init__()
        self.flow = flow
        self.text: discord.ui.TextInput[Any] = discord.ui.TextInput(
            label="Regeln-Text", style=discord.TextStyle.paragraph, default=current, max_length=1000)
        self.add_item(self.text)

    async def on_submit(self, interaction: discord.Interaction) -> None:
        try:
            await self.flow.module.set_text(self.flow.guild, str(self.text.value))
        except UserError as e:
            await interaction.response.send_message(str(e), ephemeral=True)
            return
        await self.flow.show(interaction)
