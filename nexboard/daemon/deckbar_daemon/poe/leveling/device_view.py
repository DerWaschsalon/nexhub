"""Der aktuelle Schritt als Inhalt der Guide-Kachel (nexproto.device.Guide).

Die Kachel kann keine Bilder im Text; Symbole werden zu kurzen Marken („WP“, „NE“). Farben gehen als
Farbbefehle von LVGL mit („#FEC076 The Coast#“), weiße Stücke ohne Befehl, das spart Platz.
"""
from __future__ import annotations

import re

from nexproto.device import GUIDE_LINE_MAX, GUIDE_MAX_LINES

from .markup import WHITE, Line, Rendered, Segment

SYMBOL_COLOR = "8AB3FF"
HINT_COLOR = "9AA0AA"
# (img:…) → Marke; leer = Symbol entfällt (Text danach sagt schon genug)
SYMBOLS = {
    "0": "N", "1": "NE", "2": "E", "3": "SE", "4": "S", "5": "SW", "6": "W", "7": "NW",
    "waypoint": "WP", "portal": "TP", "town": "town", "hideout": "HO", "lab": "lab", "craft": "craft",
    "in-out2": "in/out", "skip": "skip", "quest": "", "arena": "", "help": "",
}
BULLETS = {"step": "• ", "optional": "+ ", "hint": "    "}  # Unterpunkte bringen ihren Strich selbst mit
EXTRA_SPACES = re.compile(r"(?<=\S) {2,}")


def _colored(text: str, color: str) -> str:
    text = text.replace("#", "")  # # leitet bei LVGL einen Farbbefehl ein
    if not text.strip() or color.upper() == WHITE:
        return text
    return f"#{color} {text}#"


def _segment(segment: Segment, following: Segment | None) -> str:
    if not segment.image:
        return _colored(segment.text, segment.color)
    mark = SYMBOLS.get(segment.image, "")
    if not mark:
        return " "  # vor einem Symbol steht kein Leerzeichen; entfällt es, braucht es eins
    space = " " if following is None or not following.text.startswith((",", ".", ":", ")")) else ""
    return _colored(mark, SYMBOL_COLOR) + space


def device_line(line: Line) -> str:
    """Eine Zeile mit Farbbefehlen; zu lang: an einer Stückgrenze abgeschnitten."""
    out = BULLETS.get(line.bullet, "")
    for index, segment in enumerate(line.segments):
        following = line.segments[index + 1] if index + 1 < len(line.segments) else None
        piece = _segment(segment, following)
        if segment.image and out and not out[-1].isspace() and out[-1] != "(":
            piece = " " + piece  # auch davor steht im Guide kein Leerzeichen
        if len(out) + len(piece) > GUIDE_LINE_MAX - 1:
            return EXTRA_SPACES.sub(" ", out).rstrip() + "…"
        out += piece
    return EXTRA_SPACES.sub(" ", out).rstrip()


def device_lines(rendered: Rendered) -> list[str]:
    lines = [device_line(line) for line in rendered.lines]
    if len(lines) <= GUIDE_MAX_LINES:
        return lines
    hidden = len(lines) - GUIDE_MAX_LINES + 1
    return lines[:GUIDE_MAX_LINES - 1] + [_colored(f"… {hidden} weitere in der Web-UI", HINT_COLOR)]
