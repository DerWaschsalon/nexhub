"""Sicherheitsnetz für den Umbau (Schritt 0): Jede heute gespeicherte Einstellung wird nach dem Umbau
genauso gelesen. Die Referenz in golden/settings.json stammt aus dem Stand vor dem Umbau.

Ändert ein Umbauschritt einen Schlüssel oder wie ein Wert gelesen wird, schlägt der Test fehl. Gewollte
Änderungen brauchen eine Übersetzung alter Schlüssel beim Laden, nicht eine neue Referenz.
Neue Referenz nur für neue Felder: `PYTHONPATH=. python tests/test_settings_compat.py` im Ordner bot/.
"""

from __future__ import annotations

import asyncio
import json
import tempfile
from pathlib import Path
from typing import Any

from bot.db import Database
from bot.forms import SECTIONS, read_field
from bot.hubpages import Field

GOLDEN = Path(__file__).parent / "golden" / "settings.json"
GUILD = 1

# Ein typischer gespeicherter Rohwert je Feldart, so wie ihn Panel, /setup und Hub heute schreiben
STORED: dict[str, str] = {
    "channel": "123456789012345678",
    "voice": "223456789012345678",
    "role": "323456789012345678",
    "channels": "11,22,keine-id",
    "roles": "33,44",
    "bool": "1",
    "int": "7",
    "text": "Hallo {user}",
    "textarea": "Zeile eins\nZeile zwei",
}


def stored_value(f: Field) -> str:
    if f.kind == "choice":
        return str(f.options[-1])
    return STORED[f.kind]


async def read_all() -> dict[str, Any]:
    """Je Feld: Wert ohne Eintrag (Vorgabe) und Wert mit typischem Eintrag."""
    result: dict[str, Any] = {}
    with tempfile.TemporaryDirectory() as d:
        db = Database(Path(d) / "t.sqlite3")
        await db.connect()
        for section in SECTIONS.values():
            for f in section.fields:
                empty = read_field(db, GUILD, f)
                await db.set(GUILD, f.key, stored_value(f))
                result[f"{section.id}.{f.key}"] = {"empty": empty, "stored": read_field(db, GUILD, f)}
        await db.close()
    return result


def test_settings_read_like_before_rebuild() -> None:
    golden = json.loads(GOLDEN.read_text(encoding="utf-8"))
    now = asyncio.run(read_all())
    missing = sorted(set(golden) - set(now))
    assert not missing, f"Einstellungen verschwunden oder umbenannt: {missing}"
    for key, expected in golden.items():
        assert now[key] == expected, key


if __name__ == "__main__":
    GOLDEN.write_text(json.dumps(asyncio.run(read_all()), indent=1, ensure_ascii=False) + "\n", encoding="utf-8")
    print(f"Referenz geschrieben: {GOLDEN}")
