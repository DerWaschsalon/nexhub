"""Stammdaten des Guides aus Exile-UI: Zonen je Akt, Gems mit ihren Quests, Quests mit Akt und NPC."""
from __future__ import annotations

import json
from dataclasses import dataclass, field
from functools import cache
from importlib import resources
from pathlib import Path
from typing import Any

DATA_DIR = Path(str(resources.files("deckbar_daemon.poe.leveling").joinpath("data")))
FALLEN_FROM_GRACE = "fallen from grace"  # Lilly verkauft ab Akt 6 jedes Gem: das Original hängt das an jedes an
NOT_A_GEM = ("flask", "quest", "comment")


@dataclass
class Area:
    name: str
    act: int  # 1–10, 11 = Epilog
    map_name: str = ""  # Name auf der Wegpunktkarte, wenn er anders lautet


@dataclass
class LevelingData:
    areas: dict[str, Area] = field(default_factory=dict)
    gems: dict[str, dict[str, Any]] = field(default_factory=dict)
    quests: dict[str, dict[str, Any]] = field(default_factory=dict)  # Quest → {act, npc}

    def act_of(self, area_id: str) -> int:
        area = self.areas.get(area_id.lower())
        return area.act if area else 0

    def gem(self, name: str) -> dict[str, Any]:
        return self.gems.get(name) or {}


def _read(name: str) -> Any:
    return json.loads((DATA_DIR / name).read_text(encoding="utf-8"))


def _areas(acts: list[list[dict[str, Any]]]) -> dict[str, Area]:
    out = {}
    for act, areas in enumerate(acts, start=1):
        for area in areas:
            out[area["id"].lower()] = Area(area["name"], act, area.get("map_name", ""))
    return out


def _gems(raw: dict[str, Any]) -> dict[str, dict[str, Any]]:
    gems = {name: obj for name, obj in raw.items()
            if isinstance(obj, dict) and not name.startswith("_") and name != "renamed"}
    for name, obj in gems.items():
        if not any(word in name for word in NOT_A_GEM):
            obj.setdefault("quests", {})[FALLEN_FROM_GRACE] = {"vendor": []}
    return gems


@cache
def load() -> LevelingData:
    """Einmal je Prozess laden (die Dateien ändern sich nur mit einem Update)."""
    raw = _read("gems.json")
    return LevelingData(_areas(_read("areas.json")), _gems(raw), raw.get("_quests", {}))


def default_guide() -> list[Any]:
    """Der mitgelieferte Guide als eine Liste von Seiten (Akt 1 bis 10 hintereinander)."""
    return [page for act in _read("default-guide.json") for page in act]
