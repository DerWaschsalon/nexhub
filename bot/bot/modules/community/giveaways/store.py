"""Gewinnspiele und ihre Teilnehmer in der Datenbank (Tabellen `giveaways`, `giveaway_entries`)."""

from __future__ import annotations

import random
from typing import Any

from bot.db import Database
from bot.errors import UserError

HUB_LIMIT = 100


class GiveawayStore:
    def __init__(self, db: Database) -> None:
        self.db = db

    async def add(self, message_id: int, guild_id: int, channel_id: int, host_id: int, prize: str, winners: int,
                  ends: float) -> None:
        await self.db.execute(
            "INSERT INTO giveaways (message_id, guild_id, channel_id, host_id, prize, winners, ends, ended) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, 0)", (message_id, guild_id, channel_id, host_id, prize, winners, ends))

    async def get(self, guild_id: int, message_id: int) -> Any:
        row = await self.db.fetchone("SELECT * FROM giveaways WHERE message_id=? AND guild_id=?",
                                     (message_id, guild_id))
        if row is None:
            raise UserError("Kein Giveaway mit dieser Nachrichten-ID auf diesem Server gefunden.")
        return row

    async def running(self) -> list[Any]:
        return await self.db.fetchall("SELECT message_id FROM giveaways WHERE ended=0")

    async def due(self, now: float) -> list[Any]:
        return await self.db.fetchall("SELECT * FROM giveaways WHERE ended=0 AND ends<=?", (now,))

    async def is_running(self, message_id: int) -> bool:
        row = await self.db.fetchone("SELECT ended FROM giveaways WHERE message_id=?", (message_id,))
        return row is not None and not row["ended"]

    async def toggle_entry(self, message_id: int, user_id: int) -> bool:
        """An- oder abmelden; True heißt: nimmt jetzt teil."""
        if await self.db.fetchone("SELECT 1 FROM giveaway_entries WHERE message_id=? AND user_id=?",
                                  (message_id, user_id)):
            await self.db.execute("DELETE FROM giveaway_entries WHERE message_id=? AND user_id=?",
                                  (message_id, user_id))
            return False
        await self.db.execute("INSERT INTO giveaway_entries (message_id, user_id) VALUES (?, ?)",
                              (message_id, user_id))
        return True

    async def pick_winners(self, message_id: int, count: int) -> list[int]:
        rows = await self.db.fetchall("SELECT user_id FROM giveaway_entries WHERE message_id=?", (message_id,))
        ids = [int(r["user_id"]) for r in rows]
        random.shuffle(ids)
        return ids[:count]

    async def mark_ended(self, message_id: int) -> None:
        await self.db.execute("UPDATE giveaways SET ended=1 WHERE message_id=?", (message_id,))

    async def delete(self, message_id: int) -> None:
        await self.db.execute("DELETE FROM giveaway_entries WHERE message_id=?", (message_id,))
        await self.db.execute("DELETE FROM giveaways WHERE message_id=?", (message_id,))

    async def of_guild(self, guild_id: int) -> list[Any]:
        return await self.db.fetchall(
            "SELECT g.*, (SELECT COUNT(*) FROM giveaway_entries e WHERE e.message_id=g.message_id) AS n "
            "FROM giveaways g WHERE guild_id=? ORDER BY ended, ends DESC LIMIT ?", (guild_id, HUB_LIMIT))
