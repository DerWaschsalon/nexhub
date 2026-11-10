"""Einstellungen des Moderations-Logs."""

from pydantic import BaseModel

from bot.core.schema import setting


class LogSettings(BaseModel):
    log_channel: int | None = setting("channel", "Log-Kanal", group="Moderation",
                                      hint="Gelöschte/bearbeitete Nachrichten, Beitritte, Bans, …")
