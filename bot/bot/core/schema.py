"""Schema einer Einstellung: ein Pydantic-Feld mit den Angaben, die Hub-Formular, Klick-Panel und
/setup daraus bauen (Art, Beschriftung, Gruppe, Hilfe). Gespeichert wird über GuildSettings.

Arten: channel, voice, role (eine ID), channels, roles (Liste von IDs), bool, int, text, textarea,
choice (mit `options`). Felder ohne Art (z. B. Zustand wie „zuletzt gebumpt“) erscheinen nirgends.
"""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel
from pydantic import Field as PydanticField
from pydantic.config import JsonDict

from ..hubpages import Field as FormField


def setting(kind: str, label: str, default: Any = None, *, group: str = "", hint: str = "",
            minimum: int | None = None, zero_is_off: bool = False, options: tuple[str, ...] = ()) -> Any:
    """Ein Feld im Settings-Modell eines Moduls, mit allem, was ein Formular dafür braucht."""
    extra: JsonDict = {"kind": kind, "label": label, "group": group, "hint": hint, "minimum": minimum,
             "zero_is_off": zero_is_off, "options": list(options)}
    return PydanticField(default=default, json_schema_extra=extra)


def form_fields(model: type[BaseModel]) -> tuple[FormField, ...]:
    """Die Formularfelder eines Modells in ihrer Reihenfolge; Felder ohne `setting()` fehlen."""
    out = []
    for name, info in model.model_fields.items():
        extra = info.json_schema_extra
        if not isinstance(extra, dict) or "kind" not in extra:
            continue
        out.append(FormField(
            key=name, kind=str(extra["kind"]), label=str(extra["label"]), group=str(extra["group"]),
            hint=str(extra["hint"]), default=info.default, min=extra["minimum"],  # type: ignore[arg-type]
            zero_is_off=bool(extra["zero_is_off"]), options=tuple(extra["options"]),  # type: ignore[arg-type]
        ))
    return tuple(out)
