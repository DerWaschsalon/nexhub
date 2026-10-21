"""Auswertung eines NexLogs: Zusammenfassung für Run-Liste und Run-Seite (`summarize`, beim
Hochladen gespeichert) und Details eines Kampfes (`fight_detail`, beim Aufruf aus der Datei)."""
from __future__ import annotations

from nexproto import JOB_CLASSES, NexLog, player_name
from nexproto.nexlog import A2Fight

# So viel der Boss-HP muss weg sein, damit ein Kampf als Sieg zählt (wie im Daemon, runs.py)
KILL_RATIO = 0.97


BUCKET_MS = 1000  # Auflösung der DPS-Kurve


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


def _rate(part: int, total: int) -> float:
    return round(part * 100 / total, 1) if total else 0.0


def fight_detail(log: NexLog, fight: A2Fight) -> dict:
    """Ein Kampf im Detail:

    {fight, name, mob, duration_ms, killed, max_hp,
     players: [{actor, name, cls, damage, dps, skills: [{code, name, dot, damage, share, hits,
               crit, back, perfect, double}]}],                 Quoten in Prozent der Treffer
     timeline: {bucket_ms, players: [{actor, damage: [je Sekunde]}]} oder None ohne Einzeltreffer,
     deaths: [{name, t_ms, revived_ms}]}
    """
    names = {a.actorId: (player_name(log, a), JOB_CLASSES.get(a.jobId)) for a in fight.actors}
    skills: dict[int, list[dict]] = {}
    for s in fight.details.get("skills") or []:
        dmg, hits = max(0, int(s.get("dmg") or 0)), int(s.get("time") or 0)
        skills.setdefault(s["actorId"], []).append({
            "code": s.get("code"), "name": s.get("name") or f"#{s.get('code')}", "dot": bool(s.get("isDot")),
            "damage": dmg, "hits": hits, "crit": _rate(int(s.get("crit") or 0), hits),
            "back": _rate(int(s.get("back") or 0), hits), "perfect": _rate(int(s.get("perfect") or 0), hits),
            "double": _rate(int(s.get("double") or 0), hits)})
    players = []
    for actor, rows in skills.items():
        total = sum(r["damage"] for r in rows)
        if not total:
            continue
        for r in rows:
            r["share"] = _rate(r["damage"], total)
        name, cls = names.get(actor, (f"#{actor}", None))
        players.append({"actor": actor, "name": name, "cls": cls, "damage": total,
                        "dps": _dps(total, fight.durationMs),
                        "skills": sorted((r for r in rows if r["damage"]), key=lambda r: -r["damage"])})
    players.sort(key=lambda p: -p["damage"])

    timeline = None
    hits = log.hits.get(fight.id)
    if hits:
        buckets = fight.durationMs // BUCKET_MS + 1
        series = {p["actor"]: [0] * buckets for p in players}
        for t, actor, owner, _skill, damage, _multi, _flags in hits.rows:
            row = series.get(owner or actor)  # Beschwörungen zählen für ihre Figur, wie im Meter
            if row is not None and 0 <= t < buckets * BUCKET_MS:
                row[t // BUCKET_MS] += damage
        timeline = {"bucket_ms": BUCKET_MS, "players": [{"actor": a, "damage": d} for a, d in series.items()]}

    deaths = [{"name": names[d["actorId"]][0], "t_ms": int(d.get("tsMs") or 0), "revived_ms": d.get("revivedMs")}
              for d in fight.details.get("deaths") or [] if d.get("actorId") in names]
    max_hp = int(fight.details.get("maxHp") or 0)
    dealt = int(fight.details.get("totalTargetDamage") or (fight.model_extra or {}).get("totalDamage") or 0)
    return {"fight": fight.id, "name": fight.bossName, "mob": fight.mobCode, "duration_ms": fight.durationMs,
            "killed": max_hp > 0 and dealt >= max_hp * KILL_RATIO, "max_hp": max_hp,
            "players": players, "timeline": timeline, "deaths": sorted(deaths, key=lambda d: d["t_ms"])}

