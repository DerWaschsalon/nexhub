"""Einstellungen der automatischen Strafe nach Verwarnungen."""

from pydantic import BaseModel

from bot.core.schema import setting


class WarningSettings(BaseModel):
    warn_threshold: int = setting("int", "Schwelle", 0, hint="0 = aus", minimum=0, zero_is_off=True)
    warn_action: str = setting("choice", "Aktion", "timeout", options=("timeout", "kick", "ban"))
