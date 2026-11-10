"""Sprachzeit: Zeit im Sprachkanal zählt mit (Spalte `levels.voice_seconds`), nur wenn man nicht
allein ist (mindestens zwei Menschen), nicht im AFK-Kanal sitzt und nicht taub geschaltet ist. Dazu XP
je Minute, wenn `voice_xp_per_minute` gesetzt ist."""

from __future__ import annotations

import discord

TICK_S = 60
MIN_PEOPLE = 2
HOUR_S, MINUTE_S = 3600, 60


def qualifies(member: discord.Member, channel: discord.VoiceChannel | discord.StageChannel) -> bool:
    if member.bot or channel == channel.guild.afk_channel:
        return False
    if len([m for m in channel.members if not m.bot]) < MIN_PEOPLE:
        return False
    voice = member.voice
    return not (voice and (voice.self_deaf or voice.deaf))


def format_duration(seconds: int) -> str:
    hours, rest = divmod(seconds, HOUR_S)
    minutes = rest // MINUTE_S
    return f"{hours} Std. {minutes} Min." if hours else f"{minutes} Min."
