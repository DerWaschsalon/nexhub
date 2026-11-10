"""Einstellungen des Automod."""

from pydantic import BaseModel

from bot.core.schema import setting

FILTERS = "Wortfilter & Links"
CAPS = "Großbuchstaben & Emojis"


class AutomodSettings(BaseModel):
    automod_banned_words: str = setting("textarea", "Verbotene Wörter", "", group=FILTERS, hint="Durch Komma getrennt.")
    automod_link_filter: bool = setting("bool", "Nur Links zu erlaubten Domains zulassen", False, group=FILTERS)
    automod_allowed_domains: str = setting("textarea", "Erlaubte Domains", "", group=FILTERS,
                                           hint="Durch Komma getrennt.")
    automod_caps: bool = setting("bool", "Nachrichten mit zu vielen Großbuchstaben entfernen", False, group=CAPS)
    automod_emoji_limit: int = setting("int", "Emoji-Grenze pro Nachricht", 0, group=CAPS, hint="0 = aus",
                                       minimum=0, zero_is_off=True)
