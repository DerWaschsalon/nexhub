"""Einstellungen der drei Radar-Module, je Modul ein Modell (der Daemon speichert sie in <Modul>.yaml).

Alle Teile des Radars halten dasselbe Settings-Objekt; der Daemon setzt nach dem Speichern die neuen Werte
ein. `from_old()` übersetzt die frühere gemeinsame Datei ~/.config/aion2-radar.json mit deutschen Schlüsseln.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Literal

from pydantic import Field, field_validator

from ..config import _Strict

OLD_FILE = Path.home() / ".config" / "aion2-radar.json"
# Ton je Warngruppe, solange nichts anderes eingestellt ist (sonst: Ansage)
DEFAULT_SOUNDS = {"schwert": "aus", "casts": "aus", "zikel_angriffe": "aus"}


class RadarSettings(_Strict):
    """AION 2 · Radar: Cube-Radar, Karte und woher die Pakete kommen."""

    range_m: int = 150
    sound: bool = True  # Ton bei neuem Cube
    rotation: int = 0
    mirror: bool = False
    heading_up: bool = False
    map_name: str = ""  # leer = automatisch
    map_follow: bool = False
    hide_with_map: bool = True  # Overlay ausblenden, solange die Karte im Spiel offen ist
    minimap: list[int] = Field(default_factory=list)  # [x, y, Breite, Höhe] der Minikarte auf dem Bildschirm
    # „capture“ = vom Mitschnitt der Kampfdaten, ohne zweites Mitlesen; noch nicht im Spiel bestätigt
    source: Literal["tcpdump", "capture"] = "tcpdump"


class WarningSettings(_Strict):
    """AION 2 · Boss-Warnungen: was gewarnt wird und wie es klingt."""

    enabled: bool = True
    only_me: bool = True  # nur, was dich betrifft
    off: list[str] = Field(default_factory=list)  # abgeschaltete Warngruppen
    sounds: dict[str, str] = Field(default_factory=dict, validate_default=True)  # Warngruppe → aus, piep, ansage
    dungeon: str = "Feuertempel"  # auf der Seite gewählter Dungeon
    style: Literal["beides", "anweisung", "zeile"] = "beides"
    wave_sound: bool = True
    own_words: dict[str, str] = Field(default_factory=dict)  # Ruf → eigene Worte
    calls_off: list[str] = Field(default_factory=list)  # abgeschaltete Rufe
    # so nah muss eine Fläche liegen, damit sie „unter dir“ zählt (Größe und Form stehen nicht im Paket)
    area_m: float = 6.0
    auto_record: bool = False  # Lernmodus: jeden Dungeon-Lauf aufnehmen

    @field_validator("sounds")
    @classmethod
    def _with_default_sounds(cls, own: dict[str, str]) -> dict[str, str]:
        """Neue Warnungen bekommen ihren Standard-Ton auch dann, wenn schon eigene Töne gespeichert sind."""
        return {**DEFAULT_SOUNDS, **own}


class FieldBossSettings(_Strict):
    """AION 2 · Feldbosse."""

    announce: bool = True  # Ansage 5 Minuten vorher und beim Respawn


@dataclass
class Settings:
    radar: RadarSettings = field(default_factory=RadarSettings)
    warnings: WarningSettings = field(default_factory=WarningSettings)
    field_bosses: FieldBossSettings = field(default_factory=FieldBossSettings)


# Schlüssel der früheren Datei → (Teil, neuer Schlüssel). Name und Sprache stehen in den allgemeinen
# Einstellungen und fallen hier weg.
OLD_KEYS: dict[str, tuple[str, str]] = {
    "reichweite": ("radar", "range_m"), "ton": ("radar", "sound"), "drehung": ("radar", "rotation"),
    "spiegeln": ("radar", "mirror"), "kurs_oben": ("radar", "heading_up"), "karte_name": ("radar", "map_name"),
    "karte_folgen": ("radar", "map_follow"), "bei_karte_ausblenden": ("radar", "hide_with_map"),
    "minikarte": ("radar", "minimap"), "quelle": ("radar", "source"),
    "warn_an": ("warnings", "enabled"), "nur_mich": ("warnings", "only_me"), "meldung_aus": ("warnings", "off"),
    "warnton": ("warnings", "sounds"), "meldungen_dungeon": ("warnings", "dungeon"),
    "ansage_stil": ("warnings", "style"), "wellen_ton": ("warnings", "wave_sound"),
    "eigene_worte": ("warnings", "own_words"), "ruf_aus": ("warnings", "calls_off"),
    "flaeche_m": ("warnings", "area_m"), "aufnahme_auto": ("warnings", "auto_record"),
    "feldboss_ansage": ("field_bosses", "announce"),
}


def from_old(old: dict[str, Any]) -> dict[str, dict[str, Any]]:
    """Inhalt der früheren Datei, aufgeteilt nach Teil und mit den neuen Schlüsseln."""
    parts: dict[str, dict[str, Any]] = {"radar": {}, "warnings": {}, "field_bosses": {}}
    for key, value in old.items():
        if key in OLD_KEYS:
            part, new_key = OLD_KEYS[key]
            parts[part][new_key] = value
    return parts
