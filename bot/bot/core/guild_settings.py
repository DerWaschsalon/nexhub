"""Einstellungen eines Moduls je Discord-Server: lesen, prüfen, speichern.

Gespeichert wird wie bisher in der Tabelle `settings` (ein Schlüssel je Feld, Wert als Text), damit
vorhandene Server nach dem Umbau nichts neu einrichten müssen. Die Feldnamen des Modells sind die
Schlüssel. Ein ungültiger Wert fällt auf seinen Standard zurück, statt das ganze Modul zu verwerfen
(wie nexcore.SettingsStore für Dateien).
"""

from __future__ import annotations

import logging
from typing import Annotated, Any, Generic, TypeVar

from pydantic import BaseModel, BeforeValidator, ValidationError

from ..db import Database

log = logging.getLogger("thewashbot.settings")

T = TypeVar("T", bound=BaseModel)


def split_ids(value: Any) -> Any:
    """Listen von IDs stehen als "11,22" in der Tabelle; Unlesbares fällt weg wie bei db.get_ids."""
    if isinstance(value, str):
        return [int(part) for part in value.split(",") if part.strip().isdigit()]
    return value


IdList = Annotated[list[int], BeforeValidator(split_ids)]


def encode(value: Any) -> str | None:
    """Ein Wert so, wie db.set ihn bisher schrieb; None oder leere Liste löscht den Eintrag."""
    if value is None or value == []:
        return None
    if isinstance(value, bool):
        return "1" if value else "0"
    if isinstance(value, list):
        return ",".join(str(item) for item in value)
    return str(value)


class GuildSettings(Generic[T]):
    def __init__(self, db: Database, model: type[T]) -> None:
        self.db = db
        self.model = model

    def get(self, guild_id: int) -> T:
        stored = {name: self.db.get(guild_id, name) for name in self.model.model_fields}
        data = {name: value for name, value in stored.items() if value is not None}
        try:
            return self.model.model_validate(data)
        except ValidationError as e:
            bad = {str(err["loc"][0]) for err in e.errors() if err["loc"]}
            log.warning("Server %s: ungültige Felder auf Standard gesetzt: %s", guild_id, ", ".join(sorted(bad)))
            return self.model.model_validate({k: v for k, v in data.items() if k not in bad})

    async def update(self, guild_id: int, patch: dict[str, Any]) -> T:
        """Teil-Update prüfen und speichern. Ungültig: ValidationError, nichts gespeichert."""
        value = self.model.model_validate({**self.get(guild_id).model_dump(), **patch})
        for name in patch:
            await self.db.set(guild_id, name, encode(getattr(value, name)))
        return value

    def guilds_with(self, name: str) -> list[int]:
        """Server, bei denen dieses Feld gesetzt ist (z. B. ein Kanal für eine Erinnerung)."""
        return self.db.guilds_with(name)
