"""Die Tauri-Commands der Meter-Oberfläche, die der Mitschnitt beantwortet (Meter, Details, History).
Läuft deckbar-capture nicht, kommen die gespeicherten Kämpfe aus seinem History-Ordner und sonst die
Antwort, mit der die Oberfläche leer bleibt."""
from __future__ import annotations

import asyncio
import json
import re
from pathlib import Path
from typing import Any

from .capture import Capture
from .capture_process import history_root

SUMMARY_FIELDS = ("id", "bossName", "targetId", "startTimeMs", "durationMs", "totalDamage", "jobs", "jobIds",
                  "isTrain", "appVersion", "mobCode", "dungeonId")
NO_CAPTURE_STATUS = {"locked": False, "port": None, "device": "", "ip": "127.0.0.1", "localPlayerId": None,
                     "characterName": None, "characterNameFromGame": False}


def plain_id(fight_id: str) -> str:
    if not re.fullmatch(r"[A-Za-z0-9_.-]+", fight_id) or fight_id.startswith("."):
        raise ValueError(f"ungültige Kampf-ID {fight_id!r}")
    return fight_id


def member_jobs(record: dict) -> list[str]:
    """Wie FightRecord::member_jobs im Meter."""
    actors = [a for a in record.get("actors") or [] if isinstance(a, dict) and a.get("job")]
    if any(a.get("dbid") for a in actors):
        jobs = [a["job"] for a in actors if a.get("dbid")]
    else:
        jobs = [a["job"] for a in actors
                if not a.get("nickname") or not all(c.isdigit() or c in "*#" for c in a["nickname"])]
    return sorted(jobs)


def summaries(hist: Path) -> list[dict]:
    """FightSummary-Liste wie FightHistoryManager::list_fights, wenn deckbar-capture nicht läuft."""
    out = []
    for p in hist.glob("*.json") if hist.is_dir() else []:
        try:
            r = json.loads(p.read_text())
        except (OSError, ValueError):
            continue
        if not isinstance(r, dict) or "id" not in r:
            continue
        out.append({k: r.get(k) for k in SUMMARY_FIELDS} | {"isLive": False, "memberJobs": member_jobs(r)})
    out.sort(key=lambda f: f.get("startTimeMs") or 0, reverse=True)
    return out


class CaptureCommands:
    def __init__(self, capture: Capture) -> None:
        self.capture = capture

    async def request(self, cmd: str, **kw: Any) -> Any:
        return await self.capture.request(cmd, timeout=10, **kw)

    async def call(self, cmd: str, args: dict) -> Any:
        a = args.get
        req = self.request
        live = self.capture.running
        hist = history_root() / "history"
        match cmd:
            # ---- Mitschnitt
            case "debug_status":
                st = self.capture.status
                return {"port": st.get("port"), "device": st.get("device"), "ping": st.get("ping"),
                        "damageGeneration": 0, "aion2Window": bool(st.get("game")), "isAdmin": True}
            case "get_aion2_window_title":
                return await req("window_title") if live else None
            case "get_capture_status":
                return await req("capture_status") if live else dict(NO_CAPTURE_STATUS)
            case "is_capture_suspended":
                return bool(self.capture.status.get("suspended"))
            case "suspend_capture":
                return await req("suspend", on=bool(a("suspended"))) if live else None
            case "get_available_devices":
                return await req("devices") if live else []
            case "set_manual_device":
                return await req("set_device", device=str(a("device") or "")) if live else None
            case "reset_auto_detection":
                return await req("reset_detection") if live else None
            # ---- Meter
            case "get_dps_snapshot":
                return await req("snapshot") if live else None
            case "reset_combat":
                return await req("reset") if live else None
            case "set_target_mode":
                return await req("target_mode", mode=str(a("mode"))) if live else None
            case "set_character_name":
                name, manual = str(a("name") or ""), bool(a("manual"))
                return await req("set_character_name", name=name, manual=manual) if live else None
            case "bind_local_actor_id":
                actor, manual = int(a("actorId") or 0), bool(a("manual"))
                return await req("bind_local_actor_id", actor_id=actor, manual=manual) if live else None
            case "bind_local_nickname":
                actor, nickname = int(a("actorId") or 0), str(a("nickname") or "")
                return await req("bind_local_nickname", actor_id=actor, nickname=nickname) if live else None
            # ---- Details und History
            case "get_details_context":
                return await req("context") if live else {"currentTargetId": 0, "targets": [], "actors": []}
            case "get_skill_details":
                if not live:
                    raise RuntimeError("kein laufender Kampf")
                return await req("details", target_id=int(a("targetId") or 0), actor_ids=a("actorIds"),
                                 summary=bool(a("summaryOnly")))
            case "get_fight_buffs":
                target = int(a("targetId") or 0)
                return await req("buffs", target_id=target, target_ids=a("targetIds")) if live else None
            case "get_fight_history":
                return await req("history") if live else await asyncio.to_thread(summaries, hist)
            case "load_fight":
                fid = plain_id(str(a("id")))
                if live:
                    return await req("fight", fight_id=fid)
                return json.loads((hist / f"{fid}.json").read_text())
            case "delete_fight":
                fid = plain_id(str(a("id")))
                if live:
                    return await req("delete_fight", fight_id=fid)
                (hist / f"{fid}.json").unlink(missing_ok=True)
                return None
            case _:
                raise RuntimeError(f"{cmd}: in der NexBoard nicht verfügbar")
