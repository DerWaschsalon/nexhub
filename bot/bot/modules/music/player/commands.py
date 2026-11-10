"""Slash-Befehle der Musik."""

from __future__ import annotations

import asyncio
import random
from typing import TYPE_CHECKING

import discord
from discord import app_commands

from bot.core import ModuleCog
from bot.errors import UserError

from .player import LOOP_LABELS, Player, track_link
from .sources import RadioBrowser, Track, resolve

if TYPE_CHECKING:
    from . import MusicPlayer

SHORT = 10  # Sekunden, bis kurze Bestätigungen verschwinden
SUGGEST_TIMEOUT_S = 2.5
SUGGESTIONS = 15
UUID_LENGTH = 36  # Sender-ID von radio-browser.info, z. B. aus einem Vorschlag


def member_in_voice(interaction: discord.Interaction) -> discord.Member:
    member = interaction.user
    if not isinstance(member, discord.Member) or not member.voice or not member.voice.channel:
        raise UserError("Geh zuerst in einen Sprachkanal.")
    return member


def station_label(station: dict[str, str]) -> str:
    label = station.get("name", "").strip()
    bitrate = f"{station.get('bitrate')} kbit/s" if station.get("bitrate") else ""
    extra = " · ".join(x for x in (station.get("countrycode", ""), bitrate) if x)
    return f"{label} ({extra})" if extra else label


class MusicCog(ModuleCog):
    module: "MusicPlayer"

    async def joined(self, interaction: discord.Interaction) -> Player:
        member = member_in_voice(interaction)
        assert member.voice is not None and member.voice.channel is not None
        player = await self.module.join(member.guild, member.voice.channel, stay_if_busy=False)
        if isinstance(interaction.channel, discord.abc.Messageable):
            player.text_channel = interaction.channel
        return player

    @app_commands.command(name="play",
                          description="Song, Playlist oder Suche abspielen (YouTube, SoundCloud, Spotify)")
    @app_commands.describe(suche="Link oder Suchbegriff", vorne="An den Anfang der Warteschlange")
    @app_commands.guild_only()
    async def play(self, interaction: discord.Interaction, suche: str, vorne: bool = False) -> None:
        member_in_voice(interaction)
        await interaction.response.defer(thinking=True)
        tracks, name = await resolve(suche, interaction.user.id, self.module.http())
        player = await self.joined(interaction)
        was_idle = player.current is None
        self.module.add(player, tracks, front=vorne)
        await interaction.followup.send(added_text(player, tracks, name, was_idle, vorne), suppress_embeds=True)
        if not was_idle:
            await player.refresh_np()

    @app_commands.command(name="radio", description="Internetradio spielen")
    @app_commands.describe(sender="Sendername (Vorschläge erscheinen beim Tippen)",
                           url="Oder direkt eine Stream-Adresse")
    @app_commands.guild_only()
    async def radio(self, interaction: discord.Interaction, sender: str | None = None, url: str | None = None) -> None:
        if not sender and not url:
            raise UserError("Gib einen Sender oder eine Stream-Adresse an.")
        member_in_voice(interaction)
        await interaction.response.defer(thinking=True)
        track, station_id = await self.radio_track(interaction.user.id, sender, url)
        self.module.play_radio(await self.joined(interaction), track, station_id)
        await interaction.followup.send(f"📻 **{discord.utils.escape_markdown(track.title)}**")

    async def radio_track(self, user_id: int, sender: str | None, url: str | None) -> tuple[Track, str | None]:
        if url:
            if not url.startswith(("http://", "https://")):
                raise UserError("Das ist keine Stream-Adresse.")
            return Track(title=url.split("/")[2], query=url, requester_id=user_id, live=True, direct=True), None
        radio = self.module.radio
        assert radio is not None and sender is not None  # radio entsteht beim Start des Moduls
        station = await radio.station(sender) if len(sender) == UUID_LENGTH and sender.count("-") == 4 else None
        if station is None:
            found = await radio.search(sender, limit=1)
            station = found[0] if found else None
        if station is None:
            raise UserError(f"Keinen Sender „{sender}“ gefunden.")
        return RadioBrowser.to_track(station, user_id), station["stationuuid"]

    @radio.autocomplete("sender")
    async def radio_autocomplete(self, interaction: discord.Interaction,
                                 current: str) -> list[app_commands.Choice[str]]:
        if len(current) < 2 or self.module.radio is None:
            return []
        try:
            stations = await asyncio.wait_for(self.module.radio.search(current, limit=SUGGESTIONS), SUGGEST_TIMEOUT_S)
        except Exception as e:  # Vorschläge sind entbehrlich, der Befehl geht auch ohne
            self.module.log.debug("Radio-Vorschläge für %r: %r", current, e)
            return []
        return [app_commands.Choice(name=station_label(st)[:100], value=st["stationuuid"]) for st in stations]

    @app_commands.command(name="skip", description="Aktuellen Song überspringen")
    @app_commands.guild_only()
    async def skip(self, interaction: discord.Interaction) -> None:
        self.module.require_player(interaction, control=True).skip()
        await interaction.response.send_message("⏭️ Übersprungen.", delete_after=SHORT)

    @app_commands.command(name="stop", description="Musik stoppen, Warteschlange leeren, Kanal verlassen")
    @app_commands.guild_only()
    async def stop(self, interaction: discord.Interaction) -> None:
        player = self.module.require_player(interaction, control=True)
        await self.module.disconnect(player.guild)
        await interaction.response.send_message("⏹️ Gestoppt.", delete_after=SHORT)

    @app_commands.command(name="pause", description="Pausieren")
    @app_commands.guild_only()
    async def pause(self, interaction: discord.Interaction) -> None:
        vc = self.module.require_player(interaction).voice()
        if vc:
            vc.pause()
        await interaction.response.send_message("⏸️ Pausiert. Weiter mit `/weiter`.", delete_after=SHORT)

    @app_commands.command(name="weiter", description="Pause beenden")
    @app_commands.guild_only()
    async def resume(self, interaction: discord.Interaction) -> None:
        vc = self.module.require_player(interaction).voice()
        if vc:
            vc.resume()
        await interaction.response.send_message("▶️ Weiter geht's.", delete_after=SHORT)

    @app_commands.command(name="warteschlange", description="Warteschlange anzeigen")
    @app_commands.guild_only()
    async def queue(self, interaction: discord.Interaction) -> None:
        player = self.module.players.get(interaction.guild_id or 0)
        await interaction.response.send_message(embed=self.module.queue_embed(player), ephemeral=True)

    @app_commands.command(name="jetzt", description="Was läuft gerade?")
    @app_commands.guild_only()
    async def now(self, interaction: discord.Interaction) -> None:
        player = self.module.players.get(interaction.guild_id or 0)
        if player is None or player.current is None:
            raise UserError("Gerade läuft nichts.")
        await interaction.response.send_message(embed=player.np_embed(), ephemeral=True)

    @app_commands.command(name="lautstaerke", description="Lautstärke für alle (0–150 %)")
    @app_commands.guild_only()
    async def volume(self, interaction: discord.Interaction, prozent: app_commands.Range[int, 0, 150]) -> None:
        player = self.module.require_player(interaction, control=True)
        player.set_volume(prozent / 100)
        await interaction.response.send_message(f"🔊 {prozent} %", delete_after=SHORT)
        await player.refresh_np()

    @app_commands.command(name="wiederholen", description="Song oder Warteschlange wiederholen")
    @app_commands.choices(modus=[app_commands.Choice(name=v, value=k) for k, v in LOOP_LABELS.items()])
    @app_commands.guild_only()
    async def loop(self, interaction: discord.Interaction, modus: app_commands.Choice[str]) -> None:
        player = self.module.require_player(interaction)
        player.loop = modus.value
        await interaction.response.send_message(f"🔁 Wiederholen: {modus.name}", delete_after=SHORT)
        await player.refresh_np()

    @app_commands.command(name="mischen", description="Warteschlange mischen")
    @app_commands.guild_only()
    async def shuffle(self, interaction: discord.Interaction) -> None:
        player = self.module.require_player(interaction, control=True)
        random.shuffle(player.queue)
        await interaction.response.send_message("🔀 Gemischt.", delete_after=SHORT)
        await player.refresh_np()

    @app_commands.command(name="entfernen", description="Titel aus der Warteschlange entfernen")
    @app_commands.describe(platz="Nummer aus /warteschlange")
    @app_commands.guild_only()
    async def remove(self, interaction: discord.Interaction, platz: app_commands.Range[int, 1, 1000]) -> None:
        player = self.module.require_player(interaction)
        if platz > len(player.queue):
            raise UserError(f"Die Warteschlange hat nur {len(player.queue)} Titel.")
        track = player.queue[platz - 1]
        member = interaction.user
        own = track.requester_id == member.id
        if not own and not (isinstance(member, discord.Member) and self.module.may_control(member, player)):
            raise UserError("Du darfst nur eigene Titel entfernen.")
        player.queue.pop(platz - 1)
        await interaction.response.send_message(f"🗑️ {track_link(track)} entfernt.", suppress_embeds=True,
                                                delete_after=SHORT)
        await player.refresh_np()


def added_text(player: Player, tracks: list[Track], name: str | None, was_idle: bool, front: bool) -> str:
    """Rückmeldung nach /play: was dazukam und an welcher Stelle."""
    if front:
        return f"⏫ {track_link(tracks[0])} kommt als Nächstes."
    if len(tracks) == 1:
        place = "läuft gleich" if was_idle and len(player.queue) == 1 else f"Platz {len(player.queue)}"
        text = f"➕ {track_link(tracks[0])} ({place})"
    else:
        text = f"➕ **{len(tracks)} Titel**" + (f" aus **{discord.utils.escape_markdown(name)}**" if name else "")
    if player.current and player.current.live:
        text += "\n-# Gerade läuft ein Livestream, `/skip` wechselt zur Warteschlange."
    return text
