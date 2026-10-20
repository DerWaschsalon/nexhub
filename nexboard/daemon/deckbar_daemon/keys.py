"""Hotkey-Strings ("ctrl+shift+m") -> Linux-Keycodes für `ydotool key`.

Die Keycodes kommen aus /usr/include/linux/input-event-codes.h (Paket linux-api-headers)
und werden nicht hartkodiert.
"""
from __future__ import annotations

import functools
import re
from pathlib import Path

HEADER = Path("/usr/include/linux/input-event-codes.h")

ALIASES = {
    "ctrl": "LEFTCTRL", "control": "LEFTCTRL", "rctrl": "RIGHTCTRL",
    "shift": "LEFTSHIFT", "rshift": "RIGHTSHIFT",
    "alt": "LEFTALT", "altgr": "RIGHTALT",
    "super": "LEFTMETA", "meta": "LEFTMETA", "win": "LEFTMETA", "cmd": "LEFTMETA",
    "enter": "ENTER", "return": "ENTER", "esc": "ESC", "escape": "ESC",
    "del": "DELETE", "ins": "INSERT", "pgup": "PAGEUP", "pgdn": "PAGEDOWN",
    "space": "SPACE", "tab": "TAB", "backspace": "BACKSPACE",
    "print": "SYSRQ", "prtsc": "SYSRQ",
    "up": "UP", "down": "DOWN", "left": "LEFT", "right": "RIGHT",
    "plus": "KPPLUS", "minus": "MINUS",
    "play": "PLAYPAUSE", "mute": "MUTE", "volup": "VOLUMEUP", "voldown": "VOLUMEDOWN",
}


@functools.cache
def keycodes() -> dict[str, int]:
    codes: dict[str, int] = {}
    pat = re.compile(r"#define\s+KEY_([A-Z0-9_]+)\s+(0x[0-9a-fA-F]+|\d+)\b")
    for m in pat.finditer(HEADER.read_text()):
        codes[m.group(1)] = int(m.group(2), 0)
    return codes


def parse(combo: str) -> list[int]:
    """"ctrl+shift+m" -> [29, 42, 50]. Wirft ValueError bei unbekannten Tasten."""
    codes = keycodes()
    result = []
    for part in combo.lower().replace(" ", "").split("+"):
        if not part:
            raise ValueError(f"leerer Tastenname in '{combo}'")
        name = ALIASES.get(part, part.upper())
        if name not in codes:
            raise ValueError(f"unbekannte Taste '{part}'")
        result.append(codes[name])
    return result


def ydotool_args(combo: str) -> list[str]:
    """Alle Tasten drücken, dann in umgekehrter Reihenfolge loslassen."""
    codes = parse(combo)
    return [f"{c}:1" for c in codes] + [f"{c}:0" for c in reversed(codes)]
