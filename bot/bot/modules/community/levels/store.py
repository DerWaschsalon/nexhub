"""XP, Ränge und Rollen-Belohnungen in der Datenbank (Tabellen `levels` und `level_rewards`)."""

from __future__ import annotations

from typing import Any

from bot.db import Database

LEADERBOARD_SIZE = 10


def xp_for_level(level: int) -> int:
    """XP, um von `level` auf `level + 1` zu kommen (MEE6-Formel 5·l² + 50·l + 100)."""
    return 5 * level ** 2 + 50 * level + 100


def level_from_xp(xp: int) -> tuple[int, int, int]:
    """(aktuelles Level, XP im aktuellen Level, für den nächsten Aufstieg nötige XP)."""
    level = 0
    remaining = max(0, xp)
    while remaining >= xp_for_level(level):
        remaining -= xp_for_level(level)
        level += 1
    return level, remaining, xp_for_level(level)


class LevelStore:
    def __init__(self, db: Database) -> None:
        self.db = db

    async def entry(self, guild_id: int, user_id: int) -> Any:
        return await self.db.fetchone("SELECT xp, last_xp, voice_seconds FROM levels WHERE guild_id=? AND user_id=?",
                                      (guild_id, user_id))

    async def count_message(self, guild_id: int, user_id: int) -> None:
        await self.db.execute("UPDATE levels SET messages=messages+1 WHERE guild_id=? AND user_id=?",
                              (guild_id, user_id))

    async def award_message(self, guild_id: int, user_id: int, xp: int, now: float) -> None:
        await self.db.execute(
            "INSERT INTO levels (guild_id, user_id, xp, messages, last_xp) VALUES (?, ?, ?, 1, ?) "
            "ON CONFLICT(guild_id, user_id) DO UPDATE SET xp=excluded.xp, messages=messages+1, "
            "last_xp=excluded.last_xp", (guild_id, user_id, xp, now))

    async def set_xp(self, guild_id: int, user_id: int, xp: int) -> None:
        await self.db.execute("INSERT INTO levels (guild_id, user_id, xp) VALUES (?, ?, ?) "
                              "ON CONFLICT(guild_id, user_id) DO UPDATE SET xp=excluded.xp", (guild_id, user_id, xp))

    async def add_voice(self, guild_id: int, user_id: int, seconds: int, xp: int) -> None:
        await self.db.execute(
            "INSERT INTO levels (guild_id, user_id, voice_seconds, xp) VALUES (?, ?, ?, ?) "
            "ON CONFLICT(guild_id, user_id) DO UPDATE SET "
            "voice_seconds=voice_seconds+excluded.voice_seconds, xp=xp+excluded.xp", (guild_id, user_id, seconds, xp))

    async def rank_and_xp(self, guild_id: int, user_id: int) -> tuple[int, int]:
        rows = await self.db.fetchall("SELECT user_id, xp FROM levels WHERE guild_id=? ORDER BY xp DESC", (guild_id,))
        for place, row in enumerate(rows, start=1):
            if row["user_id"] == user_id:
                return place, int(row["xp"])
        return len(rows) + 1, 0

    async def top(self, guild_id: int) -> list[Any]:
        return await self.db.fetchall("SELECT user_id, xp FROM levels WHERE guild_id=? ORDER BY xp DESC LIMIT ?",
                                      (guild_id, LEADERBOARD_SIZE))

    async def rewards_up_to(self, guild_id: int, level: int) -> list[int]:
        rows = await self.db.fetchall("SELECT role_id FROM level_rewards WHERE guild_id=? AND level<=?",
                                      (guild_id, level))
        return [int(r["role_id"]) for r in rows]

    async def set_reward(self, guild_id: int, level: int, role_id: int | None) -> None:
        """Belohnungsrolle für ein Level setzen; None entfernt sie."""
        if role_id is None:
            await self.db.execute("DELETE FROM level_rewards WHERE guild_id=? AND level=?", (guild_id, level))
            return
        await self.db.execute("INSERT INTO level_rewards (guild_id, level, role_id) VALUES (?, ?, ?) "
                              "ON CONFLICT(guild_id, level) DO UPDATE SET role_id=excluded.role_id",
                              (guild_id, level, role_id))
