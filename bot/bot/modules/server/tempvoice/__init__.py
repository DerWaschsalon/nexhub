"""Eigene Sprachkanäle („Join to create“).

Wer den eingestellten Kanal betritt, bekommt einen eigenen Sprachkanal in derselben Kategorie und wird
hineinverschoben. Der Besitzer darf ihn umbenennen, begrenzen und sperren (/vc oder direkt in Discord,
er hat „Kanal verwalten“). Ist der Kanal leer, wird er gelöscht; leere Reste nach einem Neustart räumt
der Bot beim Start auf.
"""

from __future__ import annotations

from typing import ClassVar

import discord
from discord.ext import commands
from nexcore import ModuleInfo

from bot.core import BotContext, BotModule, GuildSettings
from bot.core.module import Listener
from bot.errors import UserError

from .settings import TempVoiceSettings

MAX_BITRATE = 96_000
MAX_NAME = 100


class TempVoice(BotModule):
    info: ClassVar[ModuleInfo] = ModuleInfo(
        id="server.tempvoice", name="Temp-Voice", category="Server", icon="mdi-account-voice",
        summary="Eigene Sprachkanäle, die leer wieder verschwinden.",
    )
    Settings = TempVoiceSettings

    def __init__(self, ctx: BotContext) -> None:
        super().__init__(ctx)
        self.settings = GuildSettings(ctx.db, TempVoiceSettings)
        self.cleaned = False

    def listeners(self) -> dict[str, Listener]:
        return {"on_ready": self.clean_up, "on_voice_state_update": self.on_voice_state_update}

    def cog(self) -> commands.Cog:
        from .commands import TempVoiceCog

        return TempVoiceCog(self)

    async def clean_up(self) -> None:
        """Einmal nach dem Start: Kanäle, die während eines Neustarts leer wurden, entfernen."""
        if self.cleaned:
            return
        self.cleaned = True
        for channel_id, _guild_id, _owner in await self.db.temp_channels():
            channel = self.client.get_channel(channel_id)
            if channel is None:
                await self.db.remove_temp_channel(channel_id)
            elif isinstance(channel, discord.VoiceChannel) and not channel.members:
                await self.delete(channel)

    async def delete(self, channel: discord.VoiceChannel) -> None:
        try:
            await channel.delete(reason="Temp-Voice leer")
        except discord.NotFound:
            pass
        except discord.HTTPException as e:
            self.log.warning("Temp-Voice %s löschen: %r", channel.id, e)
            return
        await self.db.remove_temp_channel(channel.id)

    async def on_voice_state_update(self, member: discord.Member, before: discord.VoiceState,
                                    after: discord.VoiceState) -> None:
        if member.bot:
            return
        hub_id = self.settings.get(member.guild.id).tempvoice_hub
        if hub_id and isinstance(after.channel, discord.VoiceChannel) and after.channel.id == hub_id:
            await self.create_for(member, after.channel)
        left = before.channel
        if isinstance(left, discord.VoiceChannel) and left != after.channel and not left.members:
            if await self.db.temp_channel_owner(left.id) is not None:
                await self.delete(left)

    async def create_for(self, member: discord.Member, hub: discord.VoiceChannel) -> None:
        guild = member.guild
        overwrites: dict[discord.Role | discord.Member | discord.Object, discord.PermissionOverwrite] = dict(
            hub.category.overwrites if hub.category else {})
        overwrites[member] = discord.PermissionOverwrite(manage_channels=True, move_members=True, connect=True,
                                                         speak=True)
        overwrites[guild.me] = discord.PermissionOverwrite(manage_channels=True, connect=True, move_members=True,
                                                           view_channel=True)
        try:
            channel = await guild.create_voice_channel(
                f"🔊 {member.display_name}"[:MAX_NAME], category=hub.category, overwrites=overwrites,
                bitrate=min(int(guild.bitrate_limit), MAX_BITRATE), reason=f"Temp-Voice für {member}")
            await self.db.add_temp_channel(channel.id, guild.id, member.id)
            await member.move_to(channel)
        except discord.HTTPException as e:
            self.log.warning("Temp-Voice anlegen %s: %r", guild.id, e)

    async def own_channel(self, member: discord.Member) -> discord.VoiceChannel:
        """Der Temp-Kanal, in dem `member` gerade ist und der ihm gehört."""
        channel = current_voice(member)
        owner = await self.db.temp_channel_owner(channel.id)
        if owner is None:
            raise UserError("Das ist kein Temp-Kanal.")
        if owner != member.id:
            raise UserError(f"Der Kanal gehört <@{owner}>.")
        return channel

    async def claim(self, member: discord.Member) -> None:
        """Kanal übernehmen, wenn der bisherige Besitzer nicht mehr drin ist."""
        channel = current_voice(member)
        owner_id = await self.db.temp_channel_owner(channel.id)
        if owner_id is None:
            raise UserError("Das ist kein Temp-Kanal.")
        if any(m.id == owner_id for m in channel.members):
            raise UserError(f"<@{owner_id}> ist noch da.")
        old = member.guild.get_member(owner_id)
        if old:
            await channel.set_permissions(old, overwrite=None)
        await channel.set_permissions(member, manage_channels=True, move_members=True, connect=True)
        await self.db.set_temp_channel_owner(channel.id, member.id)


def current_voice(member: discord.Member) -> discord.VoiceChannel:
    channel = member.voice.channel if member.voice else None
    if not isinstance(channel, discord.VoiceChannel):
        raise UserError("Du bist in keinem Sprachkanal.")
    return channel
