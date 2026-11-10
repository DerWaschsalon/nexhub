"""Verwarnungen in der Datenbank (Tabelle `warnings`)."""

from __future__ import annotations

import time
from typing import Any

from bot.db import Database
from bot.errors import UserError

HUB_LIMIT = 200


class WarningStore:
    def __init__(self, db: Database) -> None:
        self.db = db

    async def add(self, guild_id: int, user_id: int, moderator_id: int, reason: str) -> int:
        """Eintragen; zurück kommt, die wievielte Verwarnung das für das Mitglied ist."""
        await self.db.execute(
            "INSERT INTO warnings (guild_id, user_id, moderator_id, reason, created) VALUES (?, ?, ?, ?, ?)",
            (guild_id, user_id, moderator_id, reason, time.time()))
        return len(await self.of_member(guild_id, user_id))

    async def of_member(self, guild_id: int, user_id: int) -> list[Any]:
        return await self.db.fetchall(
            "SELECT id, moderator_id, reason, created FROM warnings WHERE guild_id=? AND user_id=? "
            "ORDER BY created DESC", (guild_id, user_id))

    async def of_guild(self, guild_id: int) -> list[Any]:
        return await self.db.fetchall(
            "SELECT id, user_id, moderator_id, reason, created FROM warnings WHERE guild_id=? "
            "ORDER BY created DESC LIMIT ?", (guild_id, HUB_LIMIT))

    async def delete(self, guild_id: int, warning_id: int) -> None:
        row = await self.db.fetchone("SELECT id FROM warnings WHERE id=? AND guild_id=?", (warning_id, guild_id))
        if row is None:
            raise UserError(f"Keine Verwarnung mit der ID {warning_id} gefunden.")
        await self.db.execute("DELETE FROM warnings WHERE id=?", (warning_id,))
