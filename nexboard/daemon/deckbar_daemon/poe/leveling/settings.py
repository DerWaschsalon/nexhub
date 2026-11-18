"""Was der Nutzer wählt (Einstellungen, YAML im Konfig-Ordner) und was der Guide sich merkt (Stand, JSON).

Getrennt, weil der Stand bei jedem Schritt geschrieben wird, die Einstellungen nur aus der Web-UI.
"""
from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Any, Literal

from nexcore.paths import atomic_write
from nexcore.settings import ADVANCED, HIDDEN
from pydantic import BaseModel, Field, ValidationError, model_validator

from ...config import ID, _Strict
from .pob import PobBuild
from .terms import Options

log = logging.getLogger("nexboard.poe1.leveling")

BANDIT_LABELS: dict[str, Any] = {"none": "Alle töten", "alira": "Alira", "kraityn": "Kraityn", "oak": "Oak"}


class LevelingSettings(_Strict):
    active: bool = Field(True, title="Guide läuft",
                         description="Aus: keine Seite auf der Leiste und kein automatisches Weiterschalten")
    page: ID | None = Field("poe", title="Seite auf der Leiste",
                            description="Läuft PoE und ist der Guide nicht zu Ende, zeigt die Leiste diese Seite",
                            json_schema_extra={"choices": "pages"})
    # Auswahl steht in der Build-Karte (Liste aus dem Log); leer = der nächste neue Charakter, der in
    # Twilight Strand aufsteigt (Mitspieler zählen nicht)
    character: str = Field("", max_length=32, json_schema_extra=HIDDEN)
    league_start: bool = Field(False, title="Ligastart",
                               description="Schritte für einen frischen Start ohne Ausrüstung (Quicksilver, Wegpunkte)")
    bandit: Literal["none", "alira", "kraityn", "oak"] = Field(
        "none", title="Banditen", description="Wird beim PoB-Import aus dem Build übernommen",
        json_schema_extra={"labels": BANDIT_LABELS})
    optionals: bool = Field(True, title="Optionale Schritte")
    gem_hints: bool = Field(True, title="Gems aus dem Build",
                            description="Belohnungen („take“) und Käufe („buy“) passend zum importierten Build")
    gems_all: bool = Field(False, title="Alle Quests zeigen",
                           description="Auch Quests ohne Belohnung für den Build", json_schema_extra=ADVANCED)
    level_hints: bool = Field(False, title="Stufenempfehlungen",
                              description="„recommended level“-Zeilen des Guides", json_schema_extra=ADVANCED)

    def options(self) -> Options:
        # Beim Ligastart braucht man die Gem-Hinweise immer (wie im Original)
        return Options(league_start=self.league_start, bandit=self.bandit, optionals=self.optionals,
                       gem_hints=self.gem_hints or self.league_start, gems_all=self.gems_all,
                       level_hints=self.level_hints)


class CharacterState(BaseModel):
    """Stand eines Charakters (wie ein Profil im Original): wo im Guide, welcher Build."""
    progress: int = Field(0, ge=0)
    build: PobBuild | None = None
    gem_sources: dict[str, int] = Field(default_factory=dict)  # Gem → Akt, in dem es gekauft wird


class LevelingState(BaseModel):
    characters: dict[str, CharacterState] = Field(default_factory=dict)  # "" = noch kein Charakter bekannt
    custom_guide: list[Any] | None = None  # eigener Guide (Exile-UI-Format: Liste der Akte), None = mitgelieferter

    @model_validator(mode="before")
    @classmethod
    def _one_character(cls, data: Any) -> Any:
        """Stand vom 18.11.2026 (ein Fortschritt für alle) wird zum Stand ohne Charakter."""
        if isinstance(data, dict) and "progress" in data:
            data = dict(data)
            old = {key: data.pop(key) for key in ("progress", "build", "gem_sources") if key in data}
            data.setdefault("characters", {})[""] = old
        return data


class StateFile:
    def __init__(self, path: Path) -> None:
        self.path = path
        self.value = self._load()

    def _load(self) -> LevelingState:
        try:
            return LevelingState.model_validate_json(self.path.read_text())
        except FileNotFoundError:
            return LevelingState.model_validate({})
        except (OSError, ValidationError, json.JSONDecodeError) as e:
            log.error("%s unlesbar (%s), Guide fängt von vorn an", self.path, e)
            return LevelingState.model_validate({})

    def save(self, **changes: Any) -> None:
        self.value = self.value.model_copy(update=changes)
        atomic_write(self.path, self.value.model_dump_json(exclude_none=True))

    def character(self, name: str) -> CharacterState:
        return self.value.characters.get(name) or CharacterState.model_validate({})

    def save_character(self, name: str, **changes: Any) -> None:
        characters = dict(self.value.characters)
        characters[name] = self.character(name).model_copy(update=changes)
        self.save(characters=characters)

    def adopt_unnamed(self, name: str) -> None:
        """Der erste Charakter übernimmt, was ohne Charakter eingerichtet wurde (Build, Fortschritt)."""
        characters = dict(self.value.characters)
        if name and name not in characters and "" in characters:
            characters[name] = characters.pop("")
            self.save(characters=characters)
