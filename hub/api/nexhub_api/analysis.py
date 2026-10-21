"""Auswertung eines NexLogs. Bisher nur die Zusammenfassung für Run-Liste und Run-Seite;
Kampf-Details (DPS-Kurve, Skills, Buffs) kommen später dazu."""
from __future__ import annotations

from nexproto import JOB_CLASSES, NexLog, player_name

# So viel der Boss-HP muss weg sein, damit ein Kampf als Sieg zählt (wie im Daemon, runs.py)
KILL_RATIO = 0.97


def _dps(damage: int, ms: int) -> int:
    return round(damage * 1000 / ms) if ms > 0 else 0


def summarize(log: NexLog) -> dict:
    """Bosse mit Dauer, Sieg und Schaden je Spieler, dazu die Summe über den Run.

    {"fight_ms": …, "players": [{name, cls, damage, dps}],
     "bosses": [{fight, name, mob, start_ms, duration_ms, killed, players: [...]}]}
    """
    bosses, totals = [], {}
    fight_ms = 0
    for f in log.fights:
        names = {a.actorId: (player_name(log, a), JOB_CLASSES.get(a.jobId)) for a in f.actors}
        damage: dict[int, int] = {}
        for skill in f.details.get("skills") or []:
            damage[skill["actorId"]] = damage.get(skill["actorId"], 0) + max(0, int(skill.get("dmg") or 0))
        players = sorted(
            ({"name": names.get(actor, (f"#{actor}", None))[0], "cls": names.get(actor, (None, None))[1],
              "damage": dmg, "dps": _dps(dmg, f.durationMs)} for actor, dmg in damage.items() if dmg),
            key=lambda p: -p["damage"])
        max_hp = int(f.details.get("maxHp") or 0)
        dealt = int(f.details.get("totalTargetDamage") or (f.model_extra or {}).get("totalDamage") or 0)
        bosses.append({"fight": f.id, "name": f.bossName, "mob": f.mobCode, "start_ms": f.startTimeMs,
                       "duration_ms": f.durationMs, "killed": max_hp > 0 and dealt >= max_hp * KILL_RATIO,
                       "players": players})
        fight_ms += f.durationMs
        for p in players:
            t = totals.setdefault((p["name"], p["cls"]), {"name": p["name"], "cls": p["cls"], "damage": 0})
            t["damage"] += p["damage"]
    players = sorted(totals.values(), key=lambda p: -p["damage"])
    for p in players:
        p["dps"] = _dps(p["damage"], fight_ms)
    return {"fight_ms": fight_ms, "players": players, "bosses": bosses}
