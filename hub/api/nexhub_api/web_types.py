"""Die Antwort- und Anfragetypen der Hub-API als TypeScript für das Web (hub/web/src/lib/api-types.ts), erzeugt
aus dem OpenAPI-Schema, das FastAPI aus den Modellen der Routen baut. So schreibt niemand Typen von Hand nach.

    cd hub/api && uv run python -m nexhub_api.web_types

Nach jeder Änderung an Routen oder Modellen neu erzeugen; ein Test prüft, ob die Datei aktuell ist.
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from .config import Settings
from .main import create_app

FILE = Path(__file__).resolve().parents[2] / "web" / "src" / "lib" / "api-types.ts"
HEADER = ("// Erzeugt aus den Modellen der Hub-API (hub/api/nexhub_api/web_types.py). Nicht von Hand ändern:\n"
          "// cd hub/api && uv run python -m nexhub_api.web_types\n")
# Das Schema hängt nicht an Geheimnis und Version; feste Werte, damit überall dasselbe herauskommt
SCHEMA_SETTINGS = {"hub_secret_key": "nur-fuer-das-schema", "hub_version": "schema"}
SIMPLE = {"string": "string", "integer": "number", "number": "number", "boolean": "boolean", "null": "null"}
ANY_OBJECT = "Record<string, unknown>"
Schema = dict[str, Any]


def schema() -> Schema:
    return create_app(Settings(_env_file=None, **SCHEMA_SETTINGS)).openapi()


def request_models(spec: Schema) -> set[str]:
    """Modelle, die der Browser schickt."""
    names = set()
    for operations in spec["paths"].values():
        for operation in operations.values():
            body = operation.get("requestBody", {}).get("content", {}).get("application/json", {}).get("schema", {})
            if "$ref" in body:
                names.add(body["$ref"].rsplit("/", 1)[-1])
    return names


def ts_object(node: Schema, sent: bool) -> str:
    """Antworten enthalten immer jedes Feld; in Anfragen darf fehlen, was nicht verlangt ist."""
    required = set(node.get("required", ()))
    fields = []
    for name, field in node["properties"].items():
        key = name if name.isidentifier() else json.dumps(name)
        mark = "?" if sent and name not in required else ""
        fields.append(f"\t{key}{mark}: {ts(field)};")
    return "{\n" + "\n".join(fields) + "\n}"


def ts(node: Schema, sent: bool = False) -> str:
    """Ein Schema-Knoten als TypeScript-Typ."""
    if "$ref" in node:
        return str(node["$ref"]).rsplit("/", 1)[-1]
    if "anyOf" in node:
        return " | ".join(dict.fromkeys(ts(option) for option in node["anyOf"]))
    if "enum" in node:
        return " | ".join(json.dumps(value) for value in node["enum"])
    if "const" in node:
        return json.dumps(node["const"])
    kind = node.get("type")
    if kind == "array":
        if "prefixItems" in node:
            return "[" + ", ".join(ts(item) for item in node["prefixItems"]) + "]"
        inner = ts(node.get("items", {}))
        return f"({inner})[]" if " " in inner and not inner.startswith(("{", "Record<")) else f"{inner}[]"
    if kind == "object":
        if "properties" in node:
            return ts_object(node, sent)
        values = node.get("additionalProperties")
        return f"Record<string, {ts(values)}>" if isinstance(values, dict) and values else ANY_OBJECT
    return SIMPLE.get(str(kind), "unknown")


def text() -> str:
    spec = schema()
    sent = request_models(spec)
    models = spec["components"]["schemas"]
    types = [f"export type {name} = {ts(models[name], sent=name in sent)};" for name in sorted(models)]
    return HEADER + "\n" + "\n\n".join(types) + "\n"


if __name__ == "__main__":
    FILE.write_text(text())
    print(f"{FILE} geschrieben")
