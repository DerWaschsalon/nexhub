"""AION-2: Bestzeiten und DPS-Ranglisten je Dungeon aus den Runs des NexBoards.

Gewertet werden nur vollständige Runs (alle Bosse besiegt), getrennt nach Dungeon und Schwierigkeit.
Die Rangliste der Spieler geht nach DPS, weil der Gesamtschaden mit der Kampfzeit wächst.
`aion_dedup.py` speichert jeden geposteten Run hier und zeigt die Rekorde im Post, der Befehl
`/dungeon-rangliste` (cogs/aion_rangliste.py) liest sie.
"""

from __future__ import annotations

import time
from dataclasses import dataclass, field

from .aion_format import fmt_dps, fmt_time

TOP_TIMES = 5
TOP_PLAYERS = 10
MAX_CHOICES = 25  # Discord zeigt beim Tippen höchstens 25 Vorschläge


def is_complete(run: dict) -> bool:
    return run["bosses_total"] > 0 and run["bosses_killed"] >= run["bosses_total"]


@dataclass
class RunResult:
    """Wie sich ein gerade gespeicherter Run gegen die bisherigen schlägt."""

    fight_ms: int
    best_before_ms: int | None
    place: int
    runs: int
    dps_record: dict | None = None  # {"player", "dps", "before_player", "before_dps"}
    personal_bests: list[str] = field(default_factory=list)

    def lines(self) -> str:
        """Kurze Zeilen fürs Feld „🏆 Rekorde“ im Run-Post."""
        out = [self._time_line()]
        if self.dps_record:
            out.append(self._dps_line())
        if self.personal_bests:
            out.append(f"📈 Persönliche Bestleistung: {', '.join(self.personal_bests)}")
        return "\n".join(out)

    def _time_line(self) -> str:
        if self.best_before_ms is None:
            return f"🏁 Erste Bestzeit: **{fmt_time(self.fight_ms)}**"
        if self.fight_ms < self.best_before_ms:
            return f"🏁 **Neue Bestzeit!** {fmt_time(self.fight_ms)}, vorher {fmt_time(self.best_before_ms)}"
        return f"Platz {self.place} von {self.runs} Runs · Bestzeit {fmt_time(self.best_before_ms)}"

    def _dps_line(self) -> str:
        record = self.dps_record
        line = f"🥇 **Neuer DPS-Rekord:** {record['player']} {fmt_dps(record['dps'])}"
        if record["before_player"]:
            line += f", vorher {record['before_player']} {fmt_dps(record['before_dps'])}"
        return line


class RunRecords:
    """Runs je Server speichern und daraus Bestzeiten und Ranglisten lesen."""

    def __init__(self, db):
        self.db = db

    async def save(self, guild_id: int, run: dict, players: list[dict]) -> RunResult | None:
        """Speichert einen vollständigen Run und sagt, was er verbessert hat. Unvollständig: None."""
        if not is_complete(run):
            return None
        key = (guild_id, run["dungeon"], run.get("difficulty") or "")
        best_before = await self._best_time(*key)
        top_before = await self._top_player(*key)
        personal_before = await self._personal_bests(*key)
        await self._insert(key, run, players)
        place, runs = await self._place(*key, run["fight_ms"])
        dps_record = self._dps_record(players, top_before)
        record_holder = dps_record["player"] if dps_record else None
        return RunResult(
            fight_ms=run["fight_ms"], best_before_ms=best_before, place=place, runs=runs, dps_record=dps_record,
            personal_bests=self._improved(players, personal_before, record_holder),
        )

    async def ranking(self, guild_id: int, dungeon: str, difficulty: str) -> tuple[list, list]:
        """Schnellste Runs und Spieler mit ihrer besten DPS in diesem Dungeon."""
        times = await self.db.fetchall(
            "SELECT fight_ms, players, created FROM aion_dungeon_runs "
            "WHERE guild_id=? AND dungeon=? AND difficulty=? ORDER BY fight_ms LIMIT ?",
            (guild_id, dungeon, difficulty, TOP_TIMES),
        )
        players = await self.db.fetchall(
            "SELECT p.player, MAX(p.class) AS class, MAX(p.dps) AS dps FROM aion_dungeon_players p "
            "JOIN aion_dungeon_runs r ON r.id = p.run_id "
            "WHERE r.guild_id=? AND r.dungeon=? AND r.difficulty=? "
            "GROUP BY p.player ORDER BY dps DESC LIMIT ?",
            (guild_id, dungeon, difficulty, TOP_PLAYERS),
        )
        return times, players

    async def dungeons(self, guild_id: int, typed: str) -> list[tuple[str, str]]:
        """(Dungeon, Schwierigkeit) mit gewerteten Runs, passend zum Getippten."""
        rows = await self.db.fetchall(
            "SELECT DISTINCT dungeon, difficulty FROM aion_dungeon_runs "
            "WHERE guild_id=? AND dungeon LIKE ? ORDER BY dungeon, difficulty LIMIT ?",
            (guild_id, f"%{typed}%", MAX_CHOICES),
        )
        return [(r["dungeon"], r["difficulty"]) for r in rows]

    # ---- Einzelne Abfragen ----------------------------------------------------------------

    async def _insert(self, key: tuple, run: dict, players: list[dict]) -> None:
        names = ", ".join(p["name"] for p in players)
        run_id = await self.db.execute(
            "INSERT INTO aion_dungeon_runs (guild_id, dungeon, difficulty, fight_ms, start_ms, players, created) "
            "VALUES (?, ?, ?, ?, ?, ?, ?)",
            (*key, run["fight_ms"], run["start_ms"], names, time.time()),
        )
        for p in players:
            await self.db.execute(
                "INSERT INTO aion_dungeon_players (run_id, player, class, damage, dps) VALUES (?, ?, ?, ?, ?)",
                (run_id, p["name"], p.get("cls"), p["damage"], p.get("dps") or 0),
            )

    async def _best_time(self, guild_id: int, dungeon: str, difficulty: str) -> int | None:
        row = await self.db.fetchone(
            "SELECT MIN(fight_ms) AS best FROM aion_dungeon_runs WHERE guild_id=? AND dungeon=? AND difficulty=?",
            (guild_id, dungeon, difficulty),
        )
        return row["best"] if row else None

    async def _place(self, guild_id: int, dungeon: str, difficulty: str, fight_ms: int) -> tuple[int, int]:
        row = await self.db.fetchone(
            "SELECT SUM(fight_ms < ?) AS faster, COUNT(*) AS runs FROM aion_dungeon_runs "
            "WHERE guild_id=? AND dungeon=? AND difficulty=?",
            (fight_ms, guild_id, dungeon, difficulty),
        )
        return row["faster"] + 1, row["runs"]

    async def _personal_bests(self, guild_id: int, dungeon: str, difficulty: str) -> dict[str, float]:
        rows = await self.db.fetchall(
            "SELECT p.player, MAX(p.dps) AS dps FROM aion_dungeon_players p "
            "JOIN aion_dungeon_runs r ON r.id = p.run_id "
            "WHERE r.guild_id=? AND r.dungeon=? AND r.difficulty=? GROUP BY p.player",
            (guild_id, dungeon, difficulty),
        )
        return {r["player"]: r["dps"] for r in rows}

    async def _top_player(self, guild_id: int, dungeon: str, difficulty: str) -> dict | None:
        bests = await self._personal_bests(guild_id, dungeon, difficulty)
        if not bests:
            return None
        player = max(bests, key=bests.get)
        return {"player": player, "dps": bests[player]}

    @staticmethod
    def _dps_record(players: list[dict], top_before: dict | None) -> dict | None:
        """Höchste DPS dieses Runs, wenn sie den bisherigen Dungeon-Rekord schlägt."""
        best = max(players, key=lambda p: p.get("dps") or 0)
        before_dps = top_before["dps"] if top_before else 0
        if (best.get("dps") or 0) <= before_dps:
            return None
        return {"player": best["name"], "dps": best["dps"],
                "before_player": top_before["player"] if top_before else None, "before_dps": before_dps}

    @staticmethod
    def _improved(players: list[dict], before: dict[str, float], record_holder: str | None) -> list[str]:
        """Wer seine eigene beste DPS hier verbessert hat. Der erste Run zählt nicht als Bestleistung,
        und wer gerade den Dungeon-Rekord holt, steht schon in der Zeile darüber."""
        names = []
        for p in players:
            name = p["name"]
            if name != record_holder and name in before and (p.get("dps") or 0) > before[name]:
                names.append(name)
        return names
