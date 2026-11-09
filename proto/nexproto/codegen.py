"""Erzeugt aus nexproto alles, was Programme ohne Python brauchen: JSON-Schemas, die Konstanten der
Firmware (C), der Daemon-Web-UI (JavaScript), des Hub-Webs (TypeScript) und des Mitschnitts (Rust).

    uv run python -m nexproto.codegen     schreibt alle Dateien neu

Ein Test prüft, dass die Dateien zum Code passen; von Hand geändert werden sie nie.
"""
from __future__ import annotations

import json
from collections.abc import Callable
from pathlib import Path

from pydantic import BaseModel

from . import device
from .classes import CLASSES, UNKNOWN_COLOR
from .nexlog import NexLog

REPO = Path(__file__).resolve().parents[2]
HEADER = "Erzeugt von proto/nexproto/codegen.py, nicht von Hand ändern."

# Werte, die Firmware und Web-UI mit dem Daemon teilen, unter ihrem Namen in C (DECKBAR_…) und JS
SHARED = {
    "PROTO_VERSION": device.PROTO_VERSION,
    "DEFAULT_PORT": device.DEFAULT_PORT,
    "SCREEN_W": device.SCREEN_W,
    "SCREEN_H": device.SCREEN_H,
    "HELLO_TIMEOUT_S": device.HELLO_TIMEOUT_S,
    "MAX_MESSAGE_BYTES": device.MAX_MESSAGE_BYTES,
    "MAX_PAGES": device.MAX_PAGES,
    "MAX_ITEMS_PER_PAGE": device.MAX_ITEMS_PER_PAGE,
    "MAX_COLS": device.MAX_COLS,
    "MAX_ROWS": device.MAX_ROWS,
    "ID_MAX": device.ID_MAX,
    "LABEL_MAX": device.LABEL_MAX,
    "ICON_MAX": device.ICON_MAX,
    "IMAGE_ID_MAX": device.IMAGE_ID_MAX,
    "ART_MIN": device.ART_MIN,
    "ART_MAX": device.ART_MAX,
    "BIN_HEADER_BYTES": device.BIN_HEADER_BYTES,
    "DPS_MAX_ROWS": device.DPS_MAX_ROWS,
    "DPS_DEFAULT_PLAYERS": device.DPS_DEFAULT_PLAYERS,
    "LONG_PRESS_MS": device.LONG_PRESS_MS,
    "SLIDER_EVENTS_PER_S": device.SLIDER_EVENTS_PER_S,
}


def json_schema(schema: dict, title: str) -> str:
    out = {"$schema": "https://json-schema.org/draft/2020-12/schema", "title": title, **schema}
    return json.dumps(out, indent=2, ensure_ascii=False) + "\n"


def model_schema(model: type[BaseModel]) -> str:
    return json_schema(model.model_json_schema(), model.__name__)


def protocol_schema() -> str:
    return json_schema(device.MESSAGE.json_schema(), "NexBoard protocol v1 message")


def c_header() -> str:
    lines = [f"/* {HEADER} */", "#pragma once", ""]
    lines += [f"#define DECKBAR_{name} {value}" for name, value in SHARED.items()]
    lines += ["", "/* Klassenfarben: { Schlüssel aus state.dps.rows[].cls, RGB } */", "#define DECKBAR_CLASS_COLORS \\"]
    lines += [f'    {{"{c.key}", 0x{c.color[1:].upper()}}}, \\' for c in CLASSES]
    lines += ["", f"#define DECKBAR_UNKNOWN_CLASS_COLOR 0x{UNKNOWN_COLOR[1:].upper()}", ""]
    return "\n".join(lines)


def _classes_literal() -> str:
    rows = [f'  {{ key: "{c.key}", jobId: {c.job_id}, en: "{c.name_en}", de: "{c.name_de}", color: "{c.color}" }},'
            for c in CLASSES]
    return "\n".join(rows)


def js_module() -> str:
    lines = [f"// {HEADER}"]
    lines += [f"export const {name} = {value};" for name, value in SHARED.items()]
    lines += ["", "/** AION-2-Klassen in der Reihenfolge des Spiels */", "export const CLASSES = [", _classes_literal(),
              "];", f'export const UNKNOWN_CLASS_COLOR = "{UNKNOWN_COLOR}";', ""]
    return "\n".join(lines)


def ts_module() -> str:
    lines = [f"// {HEADER}", "",
             "export type GameClass = { key: string; jobId: number; en: string; de: string; color: string };", "",
             "/** AION-2-Klassen in der Reihenfolge des Spiels */",
             "export const CLASSES: readonly GameClass[] = [", _classes_literal(), "];",
             f"export const UNKNOWN_CLASS_COLOR = '{UNKNOWN_COLOR}';", ""]
    return "\n".join(lines)


def rust_module() -> str:
    lines = [f"// {HEADER}", "", "/// (jobId, Klassen-Schlüssel) je AION-2-Klasse",
             f"pub const CLASS_KEYS: [(i32, &str); {len(CLASSES)}] = ["]
    lines += [f'    ({c.job_id}, "{c.key}"),' for c in CLASSES]
    lines += ["];", ""]
    return "\n".join(lines)


# Zieldatei (relativ zum Repo) → Erzeuger
TARGETS: dict[str, Callable[[], str]] = {
    "proto/schema/nexlog-v1.schema.json": lambda: model_schema(NexLog),
    "nexboard/docs/protocol.schema.json": protocol_schema,
    "nexboard/shared-ui/include/deckbar/proto_gen.h": c_header,
    "nexboard/daemon/deckbar_daemon/web/js/nexproto.js": js_module,
    "hub/web/src/lib/nexproto.ts": ts_module,
    "nexboard/capture/src/proto_gen.rs": rust_module,
}


def main() -> None:
    for path, render in TARGETS.items():
        (REPO / path).write_text(render(), encoding="utf-8")
        print(f"geschrieben: {path}")


if __name__ == "__main__":
    main()
