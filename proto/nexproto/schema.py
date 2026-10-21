"""JSON-Schema der Formate für Programme ohne Python (Frontend, andere Sprachen).

    uv run python -m nexproto.schema     schreibt proto/schema/*.schema.json neu

Ein Test prüft, dass die Dateien zum Code passen.
"""
from __future__ import annotations

import json
from pathlib import Path

from .nexlog import NexLog

SCHEMA_DIR = Path(__file__).resolve().parents[1] / "schema"
SCHEMAS = {"nexlog-v1.schema.json": NexLog}


def render(model) -> str:
    schema = model.model_json_schema()
    schema["$schema"] = "https://json-schema.org/draft/2020-12/schema"
    return json.dumps(schema, indent=2, ensure_ascii=False) + "\n"


def main() -> None:
    for name, model in SCHEMAS.items():
        (SCHEMA_DIR / name).write_text(render(model), encoding="utf-8")
        print(f"geschrieben: schema/{name}")


if __name__ == "__main__":
    main()
