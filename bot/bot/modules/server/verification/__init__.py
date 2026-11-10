"""Verifizierung: Neue Mitglieder sehen nur den Regel-Kanal, bis sie dort „Regeln akzeptiert“ klicken
und die Verifiziert-Rolle bekommen. Eingerichtet über /setup verifizierung oder das Klick-Panel, der
Regel-Text ist auch im NexHub änderbar."""

from __future__ import annotations

from typing import ClassVar

import discord
from nexcore import ModuleInfo

from bot.core import BotContext, BotModule, GuildSettings
from bot.core.discord_checks import can_assign
from bot.core.module import Listener
from bot.errors import UserError

from .settings import VerificationSettings

DEFAULT_TEXT = (
    "Lies dir die Regeln hier im Kanal durch. Mit Klick auf **Regeln akzeptiert** bekommst du Zugriff "
    "auf den restlichen Server."
)
ACCEPT_ID = "verify:accept"
MAX_TEXT = 4096  # Länge einer Embed-Beschreibung bei Discord
ROLE_NAME = "Verifiziert"


def rules_embed(text: str) -> discord.Embed:
    # „\n“ als Zeichenfolge, weil Slash-Befehle keine Zeilenumbrüche erlauben
    return discord.Embed(title="📜 Regeln", description=text.replace("\\n", "\n"), colour=discord.Colour.blurple())


def preview_embed(guild: discord.Guild, channel: discord.TextChannel, role: discord.Role | None) -> discord.Embed:
    affected = sum(1 for m in guild.members if not m.bot and (not role or role not in m.roles))
    e = discord.Embed(title="🔒 Verifizierung einrichten?", colour=discord.Colour.orange())
    e.add_field(name="Regel-Kanal", value=channel.mention, inline=False)
    e.add_field(name="Rolle", value=role.mention if role else f"neu: „{ROLE_NAME}“", inline=False)
    e.add_field(
        name="Was passiert",
        value=(f"• @everyone verliert „Kanäle ansehen“ serverweit\n"
               f"• {channel.mention} bleibt für alle sichtbar\n"
               f"• Die Verifiziert-Rolle bekommt „Kanäle ansehen“ automatisch zurück\n"
               f"• {affected} bestehende Mitglieder bekommen die Rolle sofort, damit niemand ausgesperrt wird\n"
               f"• Die Autorolle (falls gesetzt, z. B. „Neuling“) bekommen neue Mitglieder weiterhin sofort "
               "beim Beitritt, unabhängig von der Verifizierung"),
        inline=False,
    )
    return e


def check_setup_rights(guild: discord.Guild, role: discord.Role | None) -> None:
    """UserError, wenn der Bot die Verifizierung so nicht einrichten kann."""
    perms = guild.me.guild_permissions
    if not (perms.manage_roles and perms.manage_channels):
        raise UserError("Mir fehlen die Rechte „Rollen verwalten“ und „Kanäle verwalten“.")
    if role is not None and not can_assign(guild, role):
        raise UserError(f"{role.mention} kann ich nicht vergeben. Meine Rolle muss in den "
                        "Servereinstellungen über ihr stehen.")


class Verification(BotModule):
    info: ClassVar[ModuleInfo] = ModuleInfo(
        id="server.verification", name="Verifizierung", category="Server", icon="mdi-shield-check",
        summary="Neue Mitglieder sehen den Server erst nach „Regeln akzeptiert“.", default=True,
    )

    def __init__(self, ctx: BotContext) -> None:
        super().__init__(ctx)
        self.settings = GuildSettings(ctx.db, VerificationSettings)

    def listeners(self) -> dict[str, Listener]:
        return {"on_interaction": self.on_interaction}

    def is_active(self, guild_id: int) -> bool:
        return self.settings.get(guild_id).verify_active

    # ---- Einrichten und Abschalten -------------------------------------------------------------

    async def apply(self, guild: discord.Guild, channel: discord.TextChannel, role: discord.Role | None,
                    text: str | None, requested_by: str) -> discord.Role:
        check_setup_rights(guild, role)
        if role is None:
            role = await guild.create_role(name=ROLE_NAME, reason=f"Verifizierung durch {requested_by}")
        role_perms = role.permissions
        role_perms.update(view_channel=True)
        await role.edit(permissions=role_perms, reason="Verifizierung eingerichtet")
        await self._give_existing_members(guild, role)

        await channel.set_permissions(guild.default_role, view_channel=True,
                                      reason="Verifizierung: Regel-Kanal bleibt sichtbar")
        everyone_perms = guild.default_role.permissions
        everyone_perms.update(view_channel=False)
        await guild.default_role.edit(permissions=everyone_perms, reason=f"Verifizierung durch {requested_by}")

        message = await channel.send(embed=rules_embed(text or DEFAULT_TEXT), view=AcceptView())
        await self.settings.update(guild.id, {"verify_role": role.id, "verify_channel": channel.id,
                                              "verify_active": True, "verify_message": message.id})
        return role

    async def _give_existing_members(self, guild: discord.Guild, role: discord.Role) -> None:
        """Bestandsmitglieder bekommen die Rolle gleich, sonst wären sie nach dem Einrichten ausgesperrt."""
        for member in guild.members:
            if member.bot or role in member.roles:
                continue
            try:
                await member.add_roles(role, reason="Verifizierung eingerichtet – Bestandsmitglied")
            except discord.HTTPException as ex:
                self.log.warning("Verifizierung Bestandsrolle %s: %r", member.id, ex)

    async def turn_off(self, guild: discord.Guild, requested_by: str) -> None:
        everyone_perms = guild.default_role.permissions
        everyone_perms.update(view_channel=True)
        await guild.default_role.edit(permissions=everyone_perms, reason=f"Verifizierung aus durch {requested_by}")
        await self.settings.update(guild.id, {"verify_active": False})

    # ---- Regeln-Panel ----------------------------------------------------------------------------

    def rules_channel(self, guild: discord.Guild) -> discord.TextChannel | None:
        channel = guild.get_channel(self.settings.get(guild.id).verify_channel or 0)
        return channel if isinstance(channel, discord.TextChannel) else None

    async def rules_message(self, guild: discord.Guild) -> discord.Message | None:
        """Die Nachricht mit dem Knopf, oder None, wenn sie fehlt oder gelöscht wurde."""
        channel = self.rules_channel(guild)
        message_id = self.settings.get(guild.id).verify_message
        if channel is None or not message_id:
            return None
        try:
            return await channel.fetch_message(message_id)
        except discord.NotFound:
            return None

    async def current_text(self, guild: discord.Guild) -> str | None:
        message = await self.rules_message(guild)
        if message is None or not message.embeds:
            return None
        return message.embeds[0].description

    async def set_text(self, guild: discord.Guild, text: str) -> discord.TextChannel:
        """Text im Regeln-Panel ersetzen; gibt den Regel-Kanal zurück."""
        text = text.strip()
        if not text:
            raise UserError("Kein Text angegeben.")
        if len(text) > MAX_TEXT:
            raise UserError(f"Höchstens {MAX_TEXT} Zeichen (Discord-Grenze).")
        message = await self.rules_message(guild)
        if message is None or not isinstance(message.channel, discord.TextChannel):
            raise UserError("Kein Regeln-Panel gefunden. Einmal neu einrichten: `/setup verifizierung`.")
        embed = message.embeds[0] if message.embeds else rules_embed(text)
        embed.description = text.replace("\\n", "\n")
        await message.edit(embed=embed)
        return message.channel

    # ---- Knopf „Regeln akzeptiert“ ---------------------------------------------------------------

    async def on_interaction(self, interaction: discord.Interaction) -> None:
        if interaction.type is not discord.InteractionType.component:
            return
        custom_id = interaction.data.get("custom_id") if interaction.data else None
        if custom_id != ACCEPT_ID or not isinstance(interaction.user, discord.Member):
            return
        await interaction.response.send_message(await self.accept(interaction.user), ephemeral=True)

    async def accept(self, member: discord.Member) -> str:
        """Rolle vergeben (und die Autorolle, falls noch nicht da); Antworttext fürs Mitglied."""
        guild = member.guild
        role = guild.get_role(self.settings.get(guild.id).verify_role or 0)
        if role is None:
            return "Verifizierung ist nicht mehr eingerichtet."
        if role in member.roles:
            return "Du bist schon verifiziert."
        try:
            await member.add_roles(role, reason="Verifizierung bestätigt")
        except discord.HTTPException:
            return "Das hat nicht geklappt, sag einem Admin Bescheid."
        await self._give_autorole(member)
        return "✅ Verifiziert! Viel Spaß auf dem Server."

    async def _give_autorole(self, member: discord.Member) -> None:
        # Gehört zur Begrüßung, wird hier nur gelesen: wer vor dem Einrichten beitrat, hat sie evtl. nicht
        autorole = member.guild.get_role(self.db.get_int(member.guild.id, "autorole") or 0)
        if autorole is None or autorole in member.roles or not can_assign(member.guild, autorole):
            return
        try:
            await member.add_roles(autorole, reason="Verifizierung bestätigt – Autorolle")
        except discord.HTTPException as ex:
            self.log.warning("Autorolle nach Verifizierung %s: %r", member.id, ex)


class AcceptView(discord.ui.View):
    """Knopf unter den Regeln. Geklickt wird über on_interaction (custom_id), deshalb überlebt er Neustarts."""

    def __init__(self) -> None:
        super().__init__(timeout=None)
        self.add_item(discord.ui.Button(label="Regeln akzeptiert", emoji="✅", style=discord.ButtonStyle.success,
                                        custom_id=ACCEPT_ID))
