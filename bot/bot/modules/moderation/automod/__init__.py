"""Automod: Wortfilter, zu viele Großbuchstaben, Emoji-Spam, Links nur zu erlaubten Domains. Jeder
Verstoß löscht die Nachricht und zählt als Verwarnung durch den Bot (Ereignis WARN)."""

from __future__ import annotations

import re
from typing import ClassVar

import discord
from nexcore import ModuleInfo

from bot.core import BotContext, BotModule, GuildSettings
from bot.core.moderation import QUIET_DELETE, WARN, WarnRequest
from bot.core.module import Listener

from .settings import AutomodSettings

LINK_RE = re.compile(r"https?://([\w.-]+)", re.I)
EMOJI_RE = re.compile(r"[\U0001F300-\U0001FAFF\U00002600-\U000027BF\U00002190-\U000021FF]|<a?:\w+:\d+>")
CAPS_MIN_LETTERS = 10
CAPS_RATIO = 0.7
NOTICE_SECONDS = 15


def caps_ratio(text: str) -> float:
    letters = [c for c in text if c.isalpha()]
    if len(letters) < CAPS_MIN_LETTERS:
        return 0.0
    return sum(1 for c in letters if c.isupper()) / len(letters)


def domain_allowed(domain: str, allowed: set[str]) -> bool:
    domain = domain.lower()
    return any(domain == a or domain.endswith(f".{a}") for a in allowed)


def word_list(text: str) -> list[str]:
    """„a, b ,c“ → ["a", "b", "c"] in Kleinbuchstaben."""
    return [w.strip().lower() for w in text.split(",") if w.strip()]


def violation(content: str, settings: AutomodSettings) -> str | None:
    """Grund des ersten Verstoßes, oder None."""
    lowered = content.lower()
    if any(word in lowered for word in word_list(settings.automod_banned_words)):
        return "verbotenes Wort"
    if settings.automod_caps and caps_ratio(content) > CAPS_RATIO:
        return "zu viele Großbuchstaben"
    if settings.automod_emoji_limit and len(EMOJI_RE.findall(content)) > settings.automod_emoji_limit:
        return "Emoji-Spam"
    if settings.automod_link_filter:
        allowed = set(word_list(settings.automod_allowed_domains))
        if any(not domain_allowed(domain, allowed) for domain in LINK_RE.findall(content)):
            return "nicht erlaubter Link"
    return None


class Automod(BotModule):
    info: ClassVar[ModuleInfo] = ModuleInfo(
        id="moderation.automod", name="Automod", category="Moderation", icon="mdi-robot-angry",
        summary="Wortfilter, Großbuchstaben, Emoji-Spam und Link-Filter; jeder Verstoß ist eine Verwarnung.",
    )
    Settings = AutomodSettings

    def __init__(self, ctx: BotContext) -> None:
        super().__init__(ctx)
        self.settings = GuildSettings(ctx.db, AutomodSettings)

    def listeners(self) -> dict[str, Listener]:
        return {"on_message": self.on_message}

    async def on_message(self, message: discord.Message) -> None:
        member, channel = message.author, message.channel
        if message.guild is None or member.bot or not isinstance(member, discord.Member):
            return
        if isinstance(channel, discord.abc.GuildChannel) and channel.permissions_for(member).manage_messages:
            return
        reason = violation(message.content, self.settings.get(message.guild.id))
        if reason:
            await self.remove(message, member, reason)

    async def remove(self, message: discord.Message, member: discord.Member, reason: str) -> None:
        await self.ctx.bus.emit(QUIET_DELETE, [message.id])
        try:
            await message.delete()
            await message.channel.send(f"{member.mention}, deine Nachricht wurde entfernt ({reason}).",
                                       delete_after=NOTICE_SECONDS)
        except discord.HTTPException:
            pass  # schon weg oder kein Schreibrecht: die Verwarnung zählt trotzdem
        bot_user = member.guild.me
        await self.ctx.bus.emit(WARN, WarnRequest(member.guild, member, bot_user, f"Automod: {reason}"))
