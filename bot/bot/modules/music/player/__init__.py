"""Musik: Warteschlange je Server, Steuerung per Befehl, Knöpfen oder NexHub, Radio aus
radio-browser.info. Allein im Sprachkanal verlässt der Bot ihn nach einer Minute."""

from __future__ import annotations

import asyncio
from typing import ClassVar

import aiohttp
import discord
from discord.ext import commands
from nexcore import ModuleInfo

from bot.core import BotContext, BotModule, GuildSettings
from bot.core.module import Listener
from bot.errors import UserError
from bot.hubpages import Page

from .player import LOOP_LABELS, Player, fmt_time, track_link
from .settings import PlayerSettings
from .sources import RadioBrowser, Track

ALONE_TIMEOUT_S = 60
QUEUE_SHOWN = 15


def voice_members(vc: discord.VoiceProtocol) -> list[discord.Member]:
    channel = vc.channel
    return channel.members if isinstance(channel, discord.VoiceChannel | discord.StageChannel) else []


def channel_name(vc: discord.VoiceProtocol) -> str:
    channel = vc.channel
    return channel.mention if isinstance(channel, discord.VoiceChannel | discord.StageChannel) else "einem Kanal"


class MusicPlayer(BotModule):
    info: ClassVar[ModuleInfo] = ModuleInfo(
        id="music.player", name="Musik", category="Musik", icon="mdi-music",
        summary="YouTube, SoundCloud, Spotify und Radio im Sprachkanal, mit DJ-Rolle.",
    )
    Settings = PlayerSettings

    def __init__(self, ctx: BotContext) -> None:
        super().__init__(ctx)
        self.settings = GuildSettings(ctx.db, PlayerSettings)
        self.players: dict[int, Player] = {}
        self.session: aiohttp.ClientSession | None = None  # entsteht erst beim Start, in der laufenden Schleife
        self.radio: RadioBrowser | None = None
        self.alone_timers: dict[int, asyncio.Task[None]] = {}
        self.background: set[asyncio.Task[None]] = set()  # asyncio hält nur schwache Verweise

    async def start(self) -> None:
        self.session = aiohttp.ClientSession()
        self.radio = RadioBrowser(self.session)

    def http(self) -> aiohttp.ClientSession:
        """Die Sitzung für Quellen und Radio; vor dem Start des Moduls gibt es keine."""
        if self.session is None:
            raise UserError("Die Musik startet gerade noch.")
        return self.session

    async def shutdown(self) -> None:
        """Beim Ausschalten und beim Beenden des Bots: alle Kanäle verlassen."""
        for guild_id in list(self.players):
            guild = self.client.get_guild(guild_id)
            if guild:
                await self.disconnect(guild)
        if self.session:
            await self.session.close()
        await super().shutdown()

    def listeners(self) -> dict[str, Listener]:
        return {"on_voice_state_update": self.on_voice_state_update}

    def cog(self) -> commands.Cog:
        from .commands import MusicCog

        return MusicCog(self)

    def pages(self) -> list[Page]:
        from .hub import music_page

        return [music_page(self)]

    def in_bot_channel(self, member: discord.Member) -> bool:
        vc = member.guild.voice_client
        return bool(vc and member.voice and member.voice.channel == vc.channel)

    def may_control(self, member: discord.Member, player: Player) -> bool:
        """DJ-Rolle, Admins, wer den Titel gewünscht hat, oder wer allein mit dem Bot ist."""
        dj_role = self.settings.get(member.guild.id).dj_role
        if not dj_role or member.guild_permissions.manage_guild or any(r.id == dj_role for r in member.roles):
            return True
        if player.current and player.current.requester_id == member.id:
            return True
        vc = player.voice()
        humans = [m for m in vc.channel.members if not m.bot] if vc else []
        return len(humans) <= 1

    def require_player(self, interaction: discord.Interaction, *, control: bool = False) -> Player:
        member = interaction.user
        player = self.players.get(interaction.guild_id or 0)
        if player is None or player.voice() is None or not isinstance(member, discord.Member):
            raise UserError("Gerade läuft nichts.")
        if not self.in_bot_channel(member):
            raise UserError("Komm erst in meinen Sprachkanal.")
        if control and not self.may_control(member, player):
            raise UserError("Das dürfen nur die DJ-Rolle, Admins oder wer den Song gewünscht hat.")
        return player

    async def join(self, guild: discord.Guild, channel: discord.VoiceChannel | discord.StageChannel,
                   *, stay_if_busy: bool) -> Player:
        """In den Kanal gehen (oder wechseln) und den Player des Servers liefern. `stay_if_busy`: spielt
        der Bot schon woanders, bleibt er dort (NexHub); sonst Fehler (Befehl in Discord)."""
        perms = channel.permissions_for(guild.me)
        if not perms.connect or not perms.speak:
            raise UserError(f"Ich darf in {channel.mention} nicht beitreten oder sprechen.")
        vc = guild.voice_client
        player = self.players.get(guild.id)
        busy = bool(player and (player.current or player.queue))
        if vc is None:
            await channel.connect(self_deaf=True)
        elif vc.channel != channel and busy and not stay_if_busy:
            raise UserError(f"Ich spiele gerade in {channel_name(vc)}.")
        elif vc.channel != channel and not busy and isinstance(vc, discord.VoiceClient):
            await vc.move_to(channel)
        if player is None or player.task.done():
            player = self.players[guild.id] = Player(self, guild)
        return player

    async def disconnect(self, guild: discord.Guild) -> None:
        player = self.players.pop(guild.id, None)
        if player:
            player.queue.clear()
            player.current = None
            if player.task is not asyncio.current_task():
                player.task.cancel()
            await player.delete_np()
        timer = self.alone_timers.pop(guild.id, None)
        if timer and timer is not asyncio.current_task():
            timer.cancel()
        if guild.voice_client:
            await guild.voice_client.disconnect(force=True)

    def add(self, player: Player, tracks: list[Track], *, front: bool) -> None:
        if front:
            player.queue[0:0] = tracks
        else:
            player.queue.extend(tracks)
        player.wake()

    def play_radio(self, player: Player, track: Track, station_id: str | None) -> None:
        """Radio ersetzt, was gerade läuft; die Warteschlange bleibt."""
        if station_id and self.radio:
            click = asyncio.create_task(self.radio.click(station_id))
            self.background.add(click)
            click.add_done_callback(self.background.discard)
        player.queue.insert(0, track)
        player.loop = "aus"
        if player.current:
            player.skip()
        player.wake()

    def queue_embed(self, player: Player | None) -> discord.Embed:
        e = discord.Embed(title="📜 Warteschlange", colour=discord.Colour.blurple())
        if not player or (not player.current and not player.queue):
            e.description = "Leer. Mit `/play` geht's los."
            return e
        lines = []
        if player.current:
            length = "Live" if player.current.live else fmt_time(player.current.duration)
            lines.append(f"▶️ {track_link(player.current)} · {length}")
        for i, t in enumerate(player.queue[:QUEUE_SHOWN], 1):
            lines.append(f"`{i:>2}.` {track_link(t, 60)} · {fmt_time(t.duration)}")
        if len(player.queue) > QUEUE_SHOWN:
            lines.append(f"… und {len(player.queue) - QUEUE_SHOWN} weitere")
        total = sum(t.duration or 0 for t in player.queue)
        e.description = "\n".join(lines)
        e.set_footer(text=f"{len(player.queue)} Titel · {fmt_time(total)} · Wiederholen: {LOOP_LABELS[player.loop]}")
        return e

    async def on_voice_state_update(self, member: discord.Member, before: discord.VoiceState,
                                    after: discord.VoiceState) -> None:
        guild = member.guild
        if member == guild.me and after.channel is None:  # rausgeworfen oder Verbindung verloren
            if guild.id in self.players:
                await self.disconnect(guild)
            return
        vc = guild.voice_client
        if vc is None:
            return
        humans = [m for m in voice_members(vc) if not m.bot]
        timer = self.alone_timers.get(guild.id)
        if not humans and not timer:
            self.alone_timers[guild.id] = asyncio.create_task(self.leave_when_alone(guild))
        elif humans and timer:
            timer.cancel()
            self.alone_timers.pop(guild.id, None)

    async def leave_when_alone(self, guild: discord.Guild) -> None:
        try:
            await asyncio.sleep(ALONE_TIMEOUT_S)
            self.alone_timers.pop(guild.id, None)
            await self.disconnect(guild)
        except asyncio.CancelledError:
            pass
