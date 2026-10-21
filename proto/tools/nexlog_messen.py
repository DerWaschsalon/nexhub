"""Misst NexLog-Größen an einer echten Kampf-History (bleibt lokal, nichts wird hochgeladen).

    uv run python tools/nexlog_messen.py ~/.local/share/deckbar/aion2/history

Runs grob wie im Daemon: aufeinanderfolgende Kämpfe im selben Dungeon mit < 20 min Pause.
Jeder Run wird als NexLog gebaut, gepackt, wieder entpackt und geprüft.
"""
from __future__ import annotations

import json
import statistics
import sys
import time
from pathlib import Path

from nexproto import NexLog, pack, unpack

GAP_MS = 20 * 60_000


def runs(history: Path) -> list[list[dict]]:
    fights = sorted((json.loads(p.read_text()) for p in history.glob("*.json")), key=lambda f: f["startTimeMs"])
    out: list[list[dict]] = []
    for f in fights:
        if not f.get("dungeonId"):
            continue  # Weltbosse und Übungspuppen sind keine Runs
        last = out[-1][-1] if out else None
        if last and last["dungeonId"] == f["dungeonId"] and f["startTimeMs"] - last["startTimeMs"] - last["durationMs"] < GAP_MS:
            out[-1].append(f)
        else:
            out.append([f])
    return out


def as_nexlog(fights: list[dict]) -> NexLog:
    return NexLog.model_validate({
        "recorder": {"nexboard": "messung"},
        "run": {"dungeon_id": fights[0]["dungeonId"], "dungeon": "?", "start_ms": fights[0]["startTimeMs"],
                "end_ms": fights[-1]["startTimeMs"] + fights[-1]["durationMs"], "complete": False,
                "bosses_total": len(fights), "bosses_killed": 0},
        "fights": fights[:64],
    })


def main(history: Path) -> None:
    rows = []
    for r in runs(history):
        log = as_nexlog(r)
        raw = len(log.model_dump_json(exclude_none=True).encode())
        t = time.perf_counter()
        packed = pack(log)
        ms = (time.perf_counter() - t) * 1000
        assert unpack(packed) == log
        rows.append((len(r), raw, len(packed), ms))
    if not rows:
        sys.exit("keine Dungeon-Kämpfe gefunden")
    print(f"{len(rows)} Runs, alle gepackt, entpackt und geprüft")
    for i, name, div in ((0, "Kämpfe", 1), (1, "roh KB", 1000), (2, "gepackt KB", 1000), (3, "packen ms", 1)):
        v = sorted(x[i] for x in rows)
        print(f"{name:11} Median {statistics.median(v) / div:8.1f}   p90 {v[int(len(v) * 0.9)] / div:8.1f}   max {v[-1] / div:8.1f}")


if __name__ == "__main__":
    main(Path(sys.argv[1]).expanduser())
