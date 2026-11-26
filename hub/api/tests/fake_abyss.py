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
    """`boards` je Boss die Namen der Rangliste (stärkste zuerst); unbekannte Bosse sind leer. Bosse in
    `not_ranked` antworten wie die echte API mit HTTP 400; `fail_page` antwortet mit HTTP 500."""

    def __init__(self) -> None:
        self.calls: list[str] = []
        self.boards: dict[int, list[str]] = {8001: [f"Bogenheld{i}" for i in range(1, 6)]}
        self.not_ranked: set[int] = set()
        self.fail_page: int | None = None
        self.failing: set[int] = set()  # Bosse, deren Rangliste immer mit HTTP 500 antwortet
        self.dungeons: list[dict] = [{"id": 600123, "name": "Ferocious Horn Den", "tier": "Conquest [Hard]",
                                      "category": "Dungeon", "display": "Ferocious Horn Den (Conquest [Hard])"}]
        self.stats: dict[int, list[dict]] = {}  # Boss → Zellen der Klassenstatistik

    def __call__(self, request: httpx.Request) -> httpx.Response:
        self.calls.append(f"{request.url.path}?{request.url.query.decode()}")
        if request.url.path == "/v1/bosses":
            return httpx.Response(200, json=NEW_RAID + OLD_RAID + [
                {"mobCode": 1, "name": "Testboss", "category": "Transcendence", "tier": "Stage 4", "dungeonId": 1}])
        if request.url.path == "/v1/dungeons":
            return httpx.Response(200, json=self.dungeons)
        if request.url.path == "/v1/statistics":
            boss = int(request.url.params["fight"])
            return httpx.Response(200, json={"build": "global", "fightKey": boss, "period": "week",
                                             "cells": self.stats.get(boss, [])})
        if request.url.path == "/v1/leaderboards":
            boss = int(request.url.params["boss"])
            page = int(request.url.params.get("page", 1))
            limit = int(request.url.params.get("limit", 100))
            if boss in self.not_ranked:
                return httpx.Response(400, json={"error": "boss not ranked"})
            if page == self.fail_page or boss in self.failing:
                return httpx.Response(500)
            names = self.boards.get(boss, [])
            rows = [entry(n, 90_000 - i * 100) for i, n in enumerate(names)][(page - 1) * limit:page * limit]
            return httpx.Response(200, json={"entries": rows, "total": len(names), "page": page, "limit": limit})
        return httpx.Response(404)
