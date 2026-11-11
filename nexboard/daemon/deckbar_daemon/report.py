"""Run-Bericht (nexproto RunReport) aus einem beendeten Run: Rangliste und Run-Bild für den Discord-Post.

Geht nach dem Upload des NexLogs an den Hub (hub.py), der ihn an TheWashBot weiterleitet. Namen von Dungeon
und Bossen sind sprachunabhängig englisch, damit Meldungen verschiedener Spieler zusammenpassen.
"""
from __future__ import annotations

import base64

from nexproto.runreport import MAX_IMAGE_BYTES, ReportPlayer, RunReport

from .run_model import Player, Run, boss_name_en, dungeon_parts_en


def _players(players: dict[str, Player], ms: int) -> list[ReportPlayer]:
    secs = max(1.0, ms / 1000)
    rows = [ReportPlayer(name=p.name, cls=p.cls, damage=p.dmg, dps=round(p.dmg / secs))
            for p in players.values() if p.dmg > 0]
    return sorted(rows, key=lambda p: -p.damage)


def run_report(run: Run, image: bytes | None = None) -> RunReport:
    """Beendeter Run, Namen schon per rename aufgelöst. `image` = das Run-Bild (WebP); zu groß: ohne."""
    bosses = run.bosses()
    fight_ms = sum(b.duration_ms for b in bosses)
    name, difficulty = dungeon_parts_en(run.dungeon)
    if image is not None and len(image) > MAX_IMAGE_BYTES:
        image = None  # der Bot malt dann selbst
    return RunReport(
        dungeon=name, difficulty=difficulty, dungeon_id=run.dungeon, bosses_total=len(bosses),
        bosses_killed=run.kills, complete=run.complete, start_ms=run.start_ms, end_ms=run.end_ms,
        fight_ms=fight_ms, players=_players(run.total().players, fight_ms),
        bosses=[{"name": boss_name_en(b.mob, b.name), "mob": b.mob, "killed": b.killed,
                 "duration_ms": b.duration_ms, "players": _players(b.players, b.duration_ms)}
                for b in bosses if b.total > 0],
        image_webp=base64.b64encode(image).decode("ascii") if image else None,
    )
