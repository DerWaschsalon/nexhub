"""Einstellungen eines Moduls: laden, prüfen, speichern, Geheimnisse maskieren.

Ersetzt die Lade-/Speicher-Kopien in den Daemon-Modulen. Ein ungültiges Feld (alte Version, von Hand
vertippt) fällt auf seinen Standard zurück, statt die ganze Datei zu verwerfen. Geheime Felder
markiert das Schema mit `Field(json_schema_extra=SECRET)`.
"""
from __future__ import annotations

import logging
from collections.abc import Callable
from pathlib import Path
from typing import Any, Generic, TypeVar

import yaml
from pydantic import BaseModel, ValidationError

from .paths import atomic_write

log = logging.getLogger("nexcore.settings")

T = TypeVar("T", bound=BaseModel)
Migration = Callable[[dict[str, Any]], dict[str, Any]]
# Hinweise im Schema für das Formular der Web-UI, als Field(json_schema_extra=…), kombinierbar mit |
SECRET = {"secret": True}  # Wert verlässt den Daemon nur maskiert
ADVANCED = {"advanced": True}  # steht unter „Erweitert“
HIDDEN = {"hidden": True}  # kein Formularfeld (eigene Oberfläche oder intern)
MASK = "•" * 8  # so sieht die Web-UI ein gesetztes Geheimnis; nur Punkte zurück heißt „unverändert“


def secret_fields(model: type[BaseModel]) -> set[str]:
    return {name for name, f in model.model_fields.items()
            if isinstance(f.json_schema_extra, dict) and f.json_schema_extra.get("secret")}


def is_mask(value: Any) -> bool:
    return isinstance(value, str) and bool(value) and set(value) == {"•"}


class SettingsStore(Generic[T]):
    def __init__(self, path: Path, model: type[T], migrate: Migration | None = None, header: str = "") -> None:
        self.path = path
        self.model = model
        self.header = header  # Kommentarzeile oben in der Datei (wofür, wer sie schreibt)
        self.migrate = migrate  # alte Schlüssel übersetzen, bevor geprüft wird
        self.secrets = secret_fields(model)
        self.value: T = self.load()

    def load(self) -> T:
        try:
            data = yaml.safe_load(self.path.read_text()) or {}
        except FileNotFoundError:
            return self.model()
        except (OSError, yaml.YAMLError) as e:
            log.error("%s unlesbar (%s), nutze Standard", self.path, e)
            return self.model()
        if not isinstance(data, dict):
            log.error("%s ist kein Objekt, nutze Standard", self.path)
            return self.model()
        return self._validate(self.migrate(data) if self.migrate else data)

    def _validate(self, data: dict[str, Any]) -> T:
        try:
            return self.model.model_validate(data)
        except ValidationError as e:
            bad = {str(err["loc"][0]) for err in e.errors() if err["loc"]}
            log.warning("%s: ungültige Felder auf Standard gesetzt: %s", self.path, ", ".join(sorted(bad)))
            return self.model.model_validate({k: v for k, v in data.items() if k not in bad})

    def save(self, value: T) -> None:
        text = yaml.safe_dump(value.model_dump(mode="json", exclude_none=True), sort_keys=False, allow_unicode=True)
        head = f"# {self.header}\n" if self.header else ""
        atomic_write(self.path, head + text, 0o600 if self.secrets else 0o644)
        self.value = value

    def merge(self, patch: dict[str, Any]) -> T:
        """Teil-Update aus der Web-UI prüfen, ohne zu speichern; maskierte Geheimnisse bleiben, wie sie
        sind. Ungültig: ValidationError."""
        patch = {k: v for k, v in patch.items() if not (k in self.secrets and is_mask(v))}
        return self.model.model_validate({**self.value.model_dump(), **patch})

    def update(self, patch: dict[str, Any]) -> T:
        value = self.merge(patch)
        self.save(value)
        return value

    def public(self) -> dict[str, Any]:
        """Für die Web-UI: Geheimnisse nur als „gesetzt“ oder leer."""
        data = self.value.model_dump(mode="json")
        for name in self.secrets:
            data[name] = MASK if data.get(name) else ""
        return data

    def schema(self) -> dict[str, Any]:
        return self.model.model_json_schema()
