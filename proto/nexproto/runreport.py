"""RunReport: ein beendeter Dungeon-Run als Rangliste, für den Discord-Post des Bots.

Weg (Umbau-Konzept, Entscheidung 09.11.): NexBoard → Hub (`POST /api/runs/{id}/report`, nach dem Upload
des NexLogs) → TheWashBot (Steuer-API `POST /control/run`). Der Bot führt Meldungen mehrerer Spieler zum
selben Run zusammen. Namen von Dungeon und Bossen sind sprachunabhängig englisch, dazu die IDs.
`image_webp` ist das Run-Bild der NexBoard (Base64-WebP); fehlt es, malt der Bot selbst.
"""
from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field

MAX_IMAGE_BYTES = 4 * 1024 * 1024  # Run-Bild, gemessen 200–400 KB (gleiche Grenze wie im Bot)
MAX_IMAGE_BASE64 = MAX_IMAGE_BYTES * 4 // 3 + 4


class _Strict(BaseModel):
    model_config = ConfigDict(extra="forbid")


class ReportPlayer(_Strict):
    name: str = Field(min_length=1, max_length=64)
    cls: str | None = Field(None, max_length=32)
    damage: int = Field(ge=0)
    dps: int = Field(ge=0)


class ReportBoss(_Strict):
    name: str = Field(min_length=1, max_length=120)
    mob: int
    killed: bool
    duration_ms: int = Field(ge=0)
    players: list[ReportPlayer] = Field(min_length=1, max_length=64)


class RunReport(_Strict):
    dungeon: str = Field(min_length=1, max_length=120)
    difficulty: str | None = Field(None, max_length=40)
    dungeon_id: int
    bosses_total: int = Field(ge=0)
    bosses_killed: int = Field(ge=0)
    complete: bool
    start_ms: int
    end_ms: int
    fight_ms: int = Field(ge=0)
    players: list[ReportPlayer] = Field(min_length=1, max_length=64)
    bosses: list[ReportBoss] = Field(default_factory=list, max_length=32)
    image_webp: str | None = Field(None, max_length=MAX_IMAGE_BASE64)
