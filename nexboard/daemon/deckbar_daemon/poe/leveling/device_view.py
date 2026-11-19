"""Der aktuelle Schritt als Inhalt der Guide-Kachel (nexproto.device.Guide).

Symbole gehen als Zeichen ab U+E000 mit (nexproto.device.guide_icon), die Kachel zeichnet dafür das Bild.
Farben gehen als Farbbefehle von LVGL mit („#FEC076 The Coast#“), weiße Stücke ohne Befehl, das spart Platz.
"""
from __future__ import annotations

import re

from nexproto.device import GUIDE_LINE_MAX, GUIDE_MAX_LINES, guide_icon

from .markup import WHITE, Line, Rendered, Segment

HINT_COLOR = "9AA0AA"
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
    icon = guide_icon(segment.image)
    if not icon:
        return " "  # vor einem Symbol steht kein Leerzeichen; entfällt es, braucht es eins
    space = " " if following is None or not following.text.startswith((",", ".", ":", ")")) else ""
    return icon + space


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
