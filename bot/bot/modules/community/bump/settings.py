"""Einstellungen der Bump-Erinnerung je Server (Schlüssel wie bisher in der Tabelle settings)."""

from __future__ import annotations

from pydantic import BaseModel


class BumpSettings(BaseModel):
    bump_channel: int | None = None  # Kanal, in dem /bump getippt wird
    bump_role: int | None = None  # Rolle, die gepingt wird
    # Zustand, keine Einstellung: wann zuletzt gebumpt, ob schon erinnert
    bump_last: float | None = None
    bump_reminded: bool = False
