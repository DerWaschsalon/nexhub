"""Warteschlange und Abspiel-Schleife eines Servers, dazu die „Läuft gerade“-Nachricht.

Damit der Kanal sauber bleibt, gibt es je Server nur eine „Läuft gerade“-Nachricht: beim nächsten Titel
wird die alte gelöscht. Bei leerer Warteschlange verlässt der Bot den Kanal nach IDLE_TIMEOUT_S.
"""

from __future__ import annotations

import asyncio
import logging
import shlex
from typing import TYPE_CHECKING

import discord

from .sources import Track, stream_url

if TYPE_CHECKING:
    from . import MusicPlayer

log = logging.getLogger("thewashbot.music.player")

IDLE_TIMEOUT_S = 300
DEFAULT_VOLUME = 0.6
SAY_SECONDS = 30
FFMPEG_BEFORE = "-reconnect 1 -reconnect_streamed 1 -reconnect_delay_max 5 -nostdin"
LOOP_LABELS = {"aus": "aus", "song": "Song", "liste": "Warteschlange"}
HOUR_S, MINUTE_S = 3600, 60


def fmt_time(seconds: int | None) -> str:
    if not seconds:
        return "?"
    hours, rest = divmod(int(seconds), HOUR_S)
    minutes, secs = divmod(rest, MINUTE_S)
    return f"{hours}:{minutes:02}:{secs:02}" if hours else f"{minutes}:{secs:02}"


def track_link(track: Track, limit: int = 80) -> str:
    title = discord.utils.escape_markdown(track.title[:limit])
    return f"[{title}]({track.page_url})" if track.page_url else title


def ffmpeg_before(track: Track) -> str:
    """FFmpeg-Optionen vor der Quelle; manche Quellen brauchen eigene HTTP-Kopfzeilen."""
    if not track.headers:
        return FFMPEG_BEFORE
    header_text = "".join(f"{k}: {v}\r\n" for k, v in track.headers.items())
    return FFMPEG_BEFORE + " -headers " + shlex.quote(header_text)


class Player:
    def __init__(self, module: "MusicPlayer", guild: discord.Guild) -> None:
        self.module = module
        self.guild = guild
        self.queue: list[Track] = []
        self.current: Track | None = None
        self.loop = "aus"
        self.volume = DEFAULT_VOLUME
        self.text_channel: discord.abc.Messageable | None = None
        self.np_message: discord.Message | None = None
        self._wakeup = asyncio.Event()
        self._skipped = False
        self.task = asyncio.create_task(self._run(), name=f"player-{guild.id}")

    def voice(self) -> discord.VoiceClient | None:
        vc = self.guild.voice_client
        return vc if isinstance(vc, discord.VoiceClient) else None

    def _next(self) -> Track | None:
        prev, skipped = self.current, self._skipped
        self._skipped = False
        if prev and not skipped and self.loop == "song":
            return prev
        if prev and self.loop == "liste":
            self.queue.append(prev)
        return self.queue.pop(0) if self.queue else None

    async def _run(self) -> None:
        try:
            while await self._play_next():
                pass
        except asyncio.CancelledError:
            pass
        except Exception:  # eine kaputte Quelle darf nicht den Bot treffen, nur diesen Player
            log.exception("Player %s abgestürzt", self.guild.id)
            await self.module.disconnect(self.guild)

    async def _play_next(self) -> bool:
        """Einen Titel spielen oder auf neue warten; False beendet die Schleife."""
        track = self._next()
        if track is None:
            return await self._wait_idle()
        vc = self.voice()
        if vc is None or not vc.is_connected():
            return False
        self.current = track
        try:
            url = await stream_url(track)
        except Exception as e:  # yt-dlp & Co. werfen alles Mögliche; der Titel wird übersprungen
            log.warning("Track %r: %r", track.query, e)
            await self.say(f"⚠️ **{discord.utils.escape_markdown(track.title)}** lässt sich nicht abspielen: {e}")
            self.current = None
            return True
        await self._play(vc, track, url)
        return True

    async def _wait_idle(self) -> bool:
        self.current = None
        await self.delete_np()
        self._wakeup.clear()
        try:
            await asyncio.wait_for(self._wakeup.wait(), IDLE_TIMEOUT_S)
        except TimeoutError:
            await self.module.disconnect(self.guild)
            return False
        return True

    async def _play(self, vc: discord.VoiceClient, track: Track, url: str) -> None:
        source = discord.PCMVolumeTransformer(
            discord.FFmpegPCMAudio(url, before_options=ffmpeg_before(track), options="-vn"), volume=self.volume)
        done = asyncio.Event()
        loop = asyncio.get_running_loop()

        def after(err: Exception | None) -> None:  # läuft im Audio-Thread von discord.py
            if err:
                log.warning("Wiedergabefehler: %r", err)
            loop.call_soon_threadsafe(done.set)

        vc.play(source, after=after)
        await self.send_np()
        await done.wait()

    def wake(self) -> None:
        self._wakeup.set()

    def skip(self) -> None:
        self._skipped = True
        vc = self.voice()
        if vc and (vc.is_playing() or vc.is_paused()):
            vc.stop()

    def set_volume(self, volume: float) -> None:
        self.volume = volume
        vc = self.voice()
        if vc and isinstance(vc.source, discord.PCMVolumeTransformer):
            vc.source.volume = volume

    async def say(self, text: str) -> None:
        if self.text_channel:
            try:
                await self.text_channel.send(text, delete_after=SAY_SECONDS)
            except discord.HTTPException:
                pass

    def np_embed(self) -> discord.Embed:
        t = self.current
        if not t:
            return discord.Embed(description="Gerade läuft nichts.", colour=discord.Colour.dark_grey())
        e = discord.Embed(title="📻 Radio" if t.direct else "🎵 Läuft gerade",
                          description=f"**{track_link(t, 200)}**", colour=discord.Colour.blurple())
        e.add_field(name="Länge", value="Live" if t.live else fmt_time(t.duration))
        e.add_field(name="Gewünscht von", value=f"<@{t.requester_id}>")
        e.add_field(name="Wiederholen", value=LOOP_LABELS[self.loop])
        if self.queue:
            e.add_field(name=f"Als Nächstes ({len(self.queue)} in der Schlange)", value=track_link(self.queue[0]),
                        inline=False)
        if t.thumbnail:
            e.set_thumbnail(url=t.thumbnail)
        e.set_footer(text=f"Lautstärke {round(self.volume * 100)} %")
        return e

    async def send_np(self) -> None:
        from .views import PlayerView

        await self.delete_np()
        if self.text_channel:
            try:
                self.np_message = await self.text_channel.send(embed=self.np_embed(), view=PlayerView(self.module))
            except discord.HTTPException:
                self.np_message = None

    async def refresh_np(self) -> None:
        if self.np_message:
            try:
                await self.np_message.edit(embed=self.np_embed())
            except discord.HTTPException:
                self.np_message = None

    async def delete_np(self) -> None:
        if self.np_message:
            try:
                await self.np_message.delete()
            except discord.HTTPException:
                pass
            self.np_message = None
