"""Rollen-Panels: Rollen per Knopf selbst nehmen und abgeben.

Die Knöpfe tragen die Rollen-ID in ihrer custom_id (`rp:<id>`). Sie werden über on_interaction
beantwortet und funktionieren deshalb auch nach einem Neustart, ohne dass der Bot sich Panels merkt.
"""

from __future__ import annotations

import re
from typing import ClassVar

import discord
from discord.ext import commands
from nexcore import ModuleInfo

from bot.core import BotModule
from bot.core.discord_checks import can_assign
from bot.core.module import Listener
from bot.errors import UserError

PANEL_PREFIX = "rp:"
MAX_ROLES = 25  # Discord: höchstens 25 Knöpfe je Nachricht
# „<emoji> <@&id>“-Paare; das Emoji ist optional (Unicode oder <:name:id>)
ROLE_WITH_EMOJI = re.compile(r"(?:(<a?:\w+:\d+>|[^\x00-\x7F\s]+)\s*)?<@&(\d+)>")


def parse_roles(guild: discord.Guild, text: str) -> tuple[list[discord.Role], dict[int, str]]:
    """Rollen und ihre Emojis aus „🎮 @Gamer 🎵 @Musik“."""
    roles: list[discord.Role] = []
    emojis: dict[int, str] = {}
    for match in ROLE_WITH_EMOJI.finditer(text):
        role = guild.get_role(int(match.group(2)))
        if role is None or role in roles:
            continue
        if not can_assign(guild, role):
            raise UserError(f"{role.mention} kann ich nicht vergeben. Meine Rolle muss darüber stehen, "
                            "und ich brauche „Rollen verwalten“.")
        roles.append(role)
        if match.group(1):
            emojis[role.id] = match.group(1)
    if not roles:
        raise UserError("Keine Rollen gefunden. Erwähne sie mit @, z. B. `🎮 @Gamer 🎵 @Musik`.")
    if len(roles) > MAX_ROLES:
        raise UserError(f"Höchstens {MAX_ROLES} Rollen pro Panel.")
    return roles, emojis


class PanelView(discord.ui.View):
    def __init__(self, roles: list[discord.Role], emojis: dict[int, str]) -> None:
        super().__init__(timeout=None)
        for role in roles:
            self.add_item(discord.ui.Button(label=role.name[:80], emoji=emojis.get(role.id),
                                            style=discord.ButtonStyle.secondary,
                                            custom_id=f"{PANEL_PREFIX}{role.id}"))


def panel_embed(title: str, text: str, roles: list[discord.Role], emojis: dict[int, str]) -> discord.Embed:
    embed = discord.Embed(title=title, description=text.replace("\\n", "\n"), colour=discord.Colour.blurple())
    embed.add_field(name="Rollen", value="\n".join(f"{emojis.get(r.id, '•')} {r.mention}" for r in roles))
    return embed


class Roles(BotModule):
    info: ClassVar[ModuleInfo] = ModuleInfo(
        id="server.roles", name="Rollen-Panel", category="Server", icon="mdi-account-tag",
        summary="Nachricht mit Knöpfen, über die man sich Rollen selbst nimmt oder abgibt.",
    )

    def listeners(self) -> dict[str, Listener]:
        return {"on_interaction": self.on_interaction}

    def cog(self) -> commands.Cog:
        from .commands import RolesCog

        return RolesCog(self)

    async def on_interaction(self, interaction: discord.Interaction) -> None:
        if interaction.type is not discord.InteractionType.component or interaction.guild is None:
            return
        custom_id = str(interaction.data.get("custom_id", "")) if interaction.data else ""
        if not custom_id.startswith(PANEL_PREFIX):
            return
        role = interaction.guild.get_role(int(custom_id[len(PANEL_PREFIX):]))
        await interaction.response.send_message(await self.toggle(interaction.user, role), ephemeral=True)

    async def toggle(self, user: discord.User | discord.Member, role: discord.Role | None) -> str:
        """Rolle nehmen oder abgeben; zurück kommt die Antwort an das Mitglied."""
        if role is None:
            return "Diese Rolle gibt es nicht mehr."
        if not isinstance(user, discord.Member) or not can_assign(role.guild, role):
            return "Ich kann diese Rolle gerade nicht vergeben. Sag einem Admin Bescheid."
        try:
            if role in user.roles:
                await user.remove_roles(role, reason="Rollen-Panel")
                return f"{role.mention} entfernt."
            await user.add_roles(role, reason="Rollen-Panel")
            return f"Du hast jetzt {role.mention}."
        except discord.HTTPException:
            return "Das hat nicht geklappt."
