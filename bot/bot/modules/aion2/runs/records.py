"""AION-2: Bestzeiten und DPS-Ranglisten je Dungeon aus den Runs des NexBoards.

Gewertet werden nur vollständige Runs (alle Bosse besiegt), getrennt nach Dungeon und Schwierigkeit.
Die Rangliste der Spieler geht nach DPS, weil der Gesamtschaden mit der Kampfzeit wächst.
Diese Datei speichert und rechnet nur; den Text für Discord baut `aion_format.records_text`.
`posts.py` speichert jeden geposteten Run, `/dungeon-rangliste` (commands.py) liest.
"""

from __future__ import annotations

import time
from dataclasses import dataclass
from typing import Any

from bot.db import Database

TOP_TIMES = 5
TOP_PLAYERS = 10
MAX_CHOICES = 25  # Discord zeigt beim Tippen höchstens 25 Vorschläge

# Run und Spieler kommen als geprüfter JSON-Payload vom NexBoard (siehe aion_dedup.validate_fight_payload).
Payload = dict[str, Any]


@dataclass(frozen=True)
class DungeonKey:
    """Wonach getrennt gewertet wird. Unbekannte Schwierigkeit ist ''."""

    guild_id: int
    dungeon: str
    difficulty: str

    def params(self) -> tuple[int, str, str]:
        return self.guild_id, self.dungeon, self.difficulty


@dataclass(frozen=True)
class DpsRecord:
    """Neuer Höchstwert im Dungeon und wem er vorher gehörte (None beim ersten Run)."""

    player: str
    dps: float
    previous_player: str | None
    previous_dps: float


@dataclass(frozen=True)
class RunResult:
    """Wie sich ein gerade gespeicherter Run gegen die bisherigen schlägt."""

    fight_ms: int
    best_before_ms: int | None
    place: int
    runs: int
    dps_record: DpsRecord | None
    personal_bests: tuple[str, ...]


@dataclass(frozen=True)
class FastRun:
    fight_ms: int
    players: str
    created: float


@dataclass(frozen=True)
class PlayerBest:
    player: str
    player_class: str | None
    dps: float


def is_complete(run: Payload) -> bool:
    return bool(run["bosses_total"] > 0 and run["bosses_killed"] >= run["bosses_total"])


def player_dps(player: Payload) -> float:
    return float(player.get("dps") or 0)


class RunRecords:
    """Runs je Server speichern und daraus Bestzeiten und Ranglisten lesen."""

    def __init__(self, db: Database) -> None:
        self.db = db

    async def save(self, guild_id: int, run: Payload, players: list[Payload]) -> RunResult | None:
        """Speichert einen vollständigen Run und sagt, was er verbessert hat. Unvollständig: None."""
        if not is_complete(run):
            return None
        key = DungeonKey(guild_id, run["dungeon"], run.get("difficulty") or "")
        best_before = await self._best_time(key)
        bests_before = await self._personal_bests(key)
        await self._insert(key, run, players)
        place, runs = await self._place(key, run["fight_ms"])
        dps_record = find_dps_record(players, bests_before)
        holder = dps_record.player if dps_record else None
        return RunResult(
            fight_ms=run["fight_ms"], best_before_ms=best_before, place=place, runs=runs,
            dps_record=dps_record, personal_bests=find_personal_bests(players, bests_before, holder),
        )

    async def fastest(self, key: DungeonKey) -> list[FastRun]:
        rows = await self.db.fetchall(
            "SELECT fight_ms, players, created FROM aion_dungeon_runs "
            "WHERE guild_id=? AND dungeon=? AND difficulty=? ORDER BY fight_ms LIMIT ?",
            (*key.params(), TOP_TIMES),
        )
        return [FastRun(r["fight_ms"], r["players"], r["created"]) for r in rows]

    async def best_players(self, key: DungeonKey) -> list[PlayerBest]:
        rows = await self.db.fetchall(
            "SELECT p.player, MAX(p.class) AS class, MAX(p.dps) AS dps FROM aion_dungeon_players p "
            "JOIN aion_dungeon_runs r ON r.id = p.run_id "
            "WHERE r.guild_id=? AND r.dungeon=? AND r.difficulty=? "
            "GROUP BY p.player ORDER BY dps DESC LIMIT ?",
            (*key.params(), TOP_PLAYERS),
        )
        return [PlayerBest(r["player"], r["class"], r["dps"]) for r in rows]

    async def dungeons(self, guild_id: int, typed: str) -> list[DungeonKey]:
        """Dungeons mit gewerteten Runs, passend zum Getippten."""
        rows = await self.db.fetchall(
            "SELECT DISTINCT dungeon, difficulty FROM aion_dungeon_runs "
            "WHERE guild_id=? AND dungeon LIKE ? ORDER BY dungeon, difficulty LIMIT ?",
            (guild_id, f"%{typed}%", MAX_CHOICES),
        )
        return [DungeonKey(guild_id, r["dungeon"], r["difficulty"]) for r in rows]

    # ---- Einzelne Abfragen ----------------------------------------------------------------

    async def _insert(self, key: DungeonKey, run: Payload, players: list[Payload]) -> None:
        names = ", ".join(p["name"] for p in players)
        run_id = await self.db.execute(
            "INSERT INTO aion_dungeon_runs (guild_id, dungeon, difficulty, fight_ms, start_ms, players, created) "
            "VALUES (?, ?, ?, ?, ?, ?, ?)",
            (*key.params(), run["fight_ms"], run["start_ms"], names, time.time()),
        )
        for p in players:
            await self.db.execute(
                "INSERT INTO aion_dungeon_players (run_id, player, class, damage, dps) VALUES (?, ?, ?, ?, ?)",
                (run_id, p["name"], p.get("cls"), p["damage"], player_dps(p)),
            )

    async def _best_time(self, key: DungeonKey) -> int | None:
        row = await self.db.fetchone(
            "SELECT MIN(fight_ms) AS best FROM aion_dungeon_runs WHERE guild_id=? AND dungeon=? AND difficulty=?",
            key.params(),
        )
        return None if row is None else row["best"]

    async def _place(self, key: DungeonKey, fight_ms: int) -> tuple[int, int]:
        row = await self.db.fetchone(
            "SELECT SUM(fight_ms < ?) AS faster, COUNT(*) AS runs FROM aion_dungeon_runs "
            "WHERE guild_id=? AND dungeon=? AND difficulty=?",
            (fight_ms, *key.params()),
        )
        assert row is not None  # COUNT liefert immer eine Zeile
        return int(row["faster"]) + 1, int(row["runs"])

    async def _personal_bests(self, key: DungeonKey) -> dict[str, float]:
        rows = await self.db.fetchall(
            "SELECT p.player, MAX(p.dps) AS dps FROM aion_dungeon_players p "
            "JOIN aion_dungeon_runs r ON r.id = p.run_id "
            "WHERE r.guild_id=? AND r.dungeon=? AND r.difficulty=? GROUP BY p.player",
            key.params(),
        )
        return {r["player"]: r["dps"] for r in rows}


def find_dps_record(players: list[Payload], bests_before: dict[str, float]) -> DpsRecord | None:
    """Höchste DPS dieses Runs, wenn sie den bisherigen Höchstwert im Dungeon schlägt."""
    best = max(players, key=player_dps)
    previous_player = None
    previous_dps = 0.0
    for name, dps in bests_before.items():
        if dps > previous_dps:
            previous_player, previous_dps = name, dps
    if player_dps(best) <= previous_dps:
        return None
    return DpsRecord(best["name"], player_dps(best), previous_player, previous_dps)


def find_personal_bests(players: list[Payload], bests_before: dict[str, float], holder: str | None) -> tuple[str, ...]:
    """Wer seine eigene beste DPS hier verbessert hat. Der erste Run zählt nicht als Bestleistung,
    und wer gerade den Dungeon-Rekord holt, steht schon in dessen Zeile."""
    names = []
    for p in players:
        name = p["name"]
        if name != holder and name in bests_before and player_dps(p) > bests_before[name]:
            names.append(name)
    return tuple(names)
