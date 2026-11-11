"""Nachgebaute Abyss-Logs-API für Tests: Antworten im Format von api.abysslogs.com/v1, Inhalte erfunden."""
from __future__ import annotations

import httpx

HOST = "api.abysslogs.com"
# zwei Raids: der neuere (höhere dungeonId) hat noch keine Einträge, der ältere schon
NEW_RAID = [{"mobCode": 9001, "name": "Neuboss", "category": "Raid", "tier": "Hard", "dungeonId": 700},
            {"mobCode": 9002, "name": "Neuboss", "category": "Raid", "tier": "Normal", "dungeonId": 701}]
OLD_RAID = [{"mobCode": 8001, "name": "Altboss", "category": "Raid", "tier": "Hard", "dungeonId": 600},
            {"mobCode": 8002, "name": "Altboss", "category": "Raid", "tier": "Normal", "dungeonId": 601}]


def entry(name: str, dps: float, duration: float = 120) -> dict:
    return {"rank": 1, "region": "eu", "playerName": name, "classHint": "Ranger", "gearScore": 2600,
            "combatPower": 123_456, "dps": dps, "totalDamage": int(dps * duration), "combatDuration": duration,
            "encounterId": "", "verified": False, "createdAt": "2026-11-10T19:10:49Z"}


class FakeAbyss:
    """`boards` je Boss die Namen der Rangliste (stärkste zuerst); unbekannte Bosse sind leer."""

    def __init__(self) -> None:
        self.calls: list[str] = []
        self.boards: dict[int, list[str]] = {8001: [f"Bogenheld{i}" for i in range(1, 6)]}

    def __call__(self, request: httpx.Request) -> httpx.Response:
        self.calls.append(f"{request.url.path}?{request.url.query.decode()}")
        if request.url.path == "/v1/bosses":
            return httpx.Response(200, json=NEW_RAID + OLD_RAID + [
                {"mobCode": 1, "name": "Testboss", "category": "Transcendence", "tier": "Stage 4", "dungeonId": 1}])
        if request.url.path == "/v1/leaderboards":
            boss = int(request.url.params["boss"])
            names = self.boards.get(boss, [])
            rows = [entry(n, 90_000 - i * 1000) for i, n in enumerate(names)]
            return httpx.Response(200, json={"entries": rows, "total": len(rows), "page": 1, "limit": 100})
        return httpx.Response(404)
