"""NexLog v1: ein Dungeon-Run, wie der Daemon ihn an den Hub schickt.

Aufbau (Einzelheiten in proto/README.md):

    {"format": "nexlog", "version": 1,
     "recorder": {...},   wer aufgenommen hat (Programmversionen, Sprache)
     "run": {...},        Zusammenfassung des Daemons (Dungeon, Zeiten, Bosse)
     "you": {...},        eigener Charakter, falls bekannt
     "names": {...},      aufgelöste Namen: "Mo***n|ranger" → "Moonlin"
     "fights": [...]}     die Kampfdateien des Mitschnitts, unverändert im A2Tools-Format

Gepackt mit gzip. Die Kampfdateien bleiben roh, damit der Hub später mehr auswerten kann, ohne
dass sich das Format ändert. Von ihnen prüft das Modell nur die Felder, die der Hub sicher braucht;
alles andere wird unverändert durchgereicht.
"""
from __future__ import annotations

import gzip
import json
import zlib
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, ValidationError, model_validator

FORMAT = "nexlog"
VERSION = 1
# Gemessen (proto/README.md): größter Run 2,6 MB roh / 0,47 MB gepackt, größter Weltboss 4 MB roh
MAX_PACKED = 8 * 1024 * 1024
MAX_UNPACKED = 32 * 1024 * 1024
MAX_FIGHTS = 64


class NexLogError(ValueError):
    """Datei ist kein gültiges NexLog (kaputt, zu groß, falsche Version, Felder fehlen)."""


class _Strict(BaseModel):
    model_config = ConfigDict(extra="forbid")


class Recorder(_Strict):
    nexboard: str = Field(max_length=40)  # Version des Daemons
    capture: str | None = Field(None, max_length=80)  # Build-ID von deckbar-capture
    language: str = Field("en", max_length=8)  # Sprache der Namen in den Kampfdateien


class RunInfo(_Strict):
    dungeon_id: int
    dungeon: str = Field(max_length=120)  # englischer Name, sprachunabhängig
    difficulty: str | None = Field(None, max_length=40)
    start_ms: int  # Unix-Zeit in ms
    end_ms: int
    complete: bool  # Endboss besiegt
    bosses_total: int = Field(ge=0)
    bosses_killed: int = Field(ge=0)


class Character(_Strict):
    name: str = Field(max_length=64)
    cls: str | None = Field(None, max_length=32)  # Klassen-Schlüssel wie im Daemon ("ranger")


class _A2(BaseModel):
    # A2Tools-Format: unbekannte Felder bleiben erhalten, neue Meter-Versionen brechen nichts
    model_config = ConfigDict(extra="allow")


class A2Actor(_A2):
    actorId: int
    nickname: str  # fremde Namen maskiert ("Mo***n"), siehe NexLog.names
    jobId: int | None = None


class A2Fight(_A2):
    id: str = Field(max_length=64)
    bossName: str
    mobCode: int
    dungeonId: int
    startTimeMs: int
    durationMs: int = Field(ge=0)
    actors: list[A2Actor]
    details: dict  # Skills, Heilung, Tode, Ping; wertet erst der Hub aus


class NexLog(_Strict):
    format: Literal["nexlog"] = FORMAT
    version: Literal[1] = VERSION
    recorder: Recorder
    run: RunInfo
    you: Character | None = None
    names: dict[str, str] = Field(default_factory=dict, max_length=500)
    fights: list[A2Fight] = Field(min_length=1, max_length=MAX_FIGHTS)

    @model_validator(mode="after")
    def _fights_belong_to_run(self) -> NexLog:
        if any(f.dungeonId != self.run.dungeon_id for f in self.fights):
            raise ValueError("alle Kämpfe müssen aus dem Dungeon des Runs stammen")
        return self


def pack(log: NexLog) -> bytes:
    """NexLog → gzip-gepacktes JSON (UTF-8)."""
    raw = log.model_dump_json(exclude_none=True).encode()
    return gzip.compress(raw, compresslevel=6, mtime=0)


def unpack(data: bytes) -> NexLog:
    """Gepacktes NexLog prüfen und lesen. Wirft NexLogError mit einem lesbaren Grund."""
    if len(data) > MAX_PACKED:
        raise NexLogError(f"Datei zu groß ({len(data)} Bytes, höchstens {MAX_PACKED})")
    # Entpacken mit Obergrenze, damit eine kleine Datei nicht Gigabytes erzeugen kann
    inflater = zlib.decompressobj(wbits=31)  # 31 = gzip-Kopf erwartet
    try:
        raw = inflater.decompress(data, MAX_UNPACKED + 1)
    except zlib.error as e:
        raise NexLogError(f"kein gültiges gzip: {e}") from None
    if len(raw) > MAX_UNPACKED:
        raise NexLogError(f"entpackt zu groß (über {MAX_UNPACKED} Bytes)")
    if not inflater.eof:
        raise NexLogError("gzip-Daten unvollständig")
    try:
        doc = json.loads(raw)
    except ValueError as e:
        raise NexLogError(f"kein gültiges JSON: {e}") from None
    if not isinstance(doc, dict) or doc.get("format") != FORMAT:
        raise NexLogError("kein NexLog")
    if doc.get("version") != VERSION:
        raise NexLogError(f"NexLog-Version {doc.get('version')!r} wird nicht unterstützt (erwartet {VERSION})")
    try:
        return NexLog.model_validate(doc)
    except ValidationError as e:
        raise NexLogError(f"ungültiges NexLog: {e.error_count()} Fehler, z. B. {_first_error(e)}") from None


def _first_error(e: ValidationError) -> str:
    err = e.errors()[0]
    return f"{'.'.join(str(p) for p in err['loc'])}: {err['msg']}"
