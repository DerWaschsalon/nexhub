"""Einstellungen der Bump-Erinnerung je Server (Schlüssel wie bisher in der Tabelle settings)."""

from __future__ import annotations

from pydantic import BaseModel

from bot.core.schema import setting

GROUP = "Bump-Erinnerung (Disboard)"


class BumpSettings(BaseModel):
    bump_channel: int | None = setting("channel", "Kanal, in dem ihr /bump nutzt", group=GROUP)
    bump_role: int | None = setting("role", "Rolle, die gepingt wird", group=GROUP)
    # Zustand, keine Einstellung: wann zuletzt gebumpt, ob schon erinnert
    bump_last: float | None = None
    bump_reminded: bool = False
