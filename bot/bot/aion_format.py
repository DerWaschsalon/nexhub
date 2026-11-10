"""AION-2: Zahlen und Zeiten, wie sie in Posts, Bildern und der Bestenliste stehen."""

from __future__ import annotations


def fmt_num(n: float) -> str:
    n = float(n)
    if n >= 1_000_000:
        return f"{n / 1_000_000:.2f}M"
    if n >= 1_000:
        return f"{n / 1_000:.1f}k"
    return f"{n:.0f}"


def fmt_dps(n: float) -> str:
    return f"{fmt_num(n)}/s"


def fmt_time(ms: float) -> str:
    """Kampfzeit als m:ss."""
    minutes, seconds = divmod(round(ms / 1000), 60)
    return f"{minutes}:{seconds:02d}"
