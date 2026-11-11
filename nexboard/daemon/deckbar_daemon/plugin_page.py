"""Was eine Plugin-Seite vom Host mitbekommt: Farben, Schriften, Content-Security-Policy."""
from __future__ import annotations

import base64
import re
from pathlib import Path
from typing import Any

from .plugin_files import valid_id

HEX_COLOR = re.compile(r"#[0-9a-fA-F]{6}")


def clean_theme(theme: Any) -> dict | None:
    """Genau die drei Farben, je #rrggbb: sie landen als CSS auf den Plugin-Seiten."""
    if not isinstance(theme, dict):
        return None
    colors = {k: theme.get(k) for k in ("bg", "panel", "accent")}
    return colors if all(isinstance(c, str) and HEX_COLOR.fullmatch(c) for c in colors.values()) else None


# ---------------------------------------------------------------- Auslieferung der Plugin-Dateien
FONTS = Path(__file__).resolve().parents[2] / "capture" / "a2tools" / "src-tauri" / "src" / "plugins" / "fonts"
TEXT_RANGE = ("font-weight:45 920;unicode-range:U+0000-00FF,U+0131,U+0152-0153,U+02BB-02BC,U+02C6,U+02DA,U+02DC,"
              "U+2000-206F,U+2074,U+20AC,U+2122,U+2190-2199,U+2212,U+2215;")
_font_style: str | None = None


def font_style() -> str:
    """Die Schriften des Meters, die Plugin-Seiten erwarten (wie with_meter_fonts im Original)."""
    global _font_style
    if _font_style is None:
        def face(family: str, file: str, extra: str) -> str:
            try:
                data = base64.b64encode((FONTS / file).read_bytes()).decode()
            except OSError:
                return ""
            return f'@font-face{{font-family:"{family}";src:url(data:font/woff2;base64,{data}) format("woff2");{extra}}}'
        _font_style = "<style>" + face("Pretendard", "PretendardLatin.woff2", TEXT_RANGE) \
            + face("Segoe UI", "PretendardLatin.woff2", TEXT_RANGE) \
            + face("Bahnschrift", "Saira.woff2", "font-weight:100 900;font-stretch:50% 125%;") + "</style>"
    return _font_style


def with_fonts(page: str) -> str:
    i = page.lower().find("<head")
    at = page.find(">", i) + 1 if i >= 0 else 0
    return page[:at] + font_style() + page[at:]


def content_policy(origin: str, prefix: str, plugin: str) -> str:
    """Nur der eigene Ordner und das SDK, kein Netz (content_policy im Original)."""
    own = f"'self' {origin}/_sdk/a2.js"
    if valid_id(plugin):
        own += f" {origin}{prefix}{plugin}/"
    return (f"default-src 'none'; script-src {own}; style-src {own} 'unsafe-inline'; img-src {own} data:; "
            f"font-src {own} data:; media-src {own}; connect-src 'none'; frame-src 'none'; base-uri 'none'; "
            "form-action 'none'")
