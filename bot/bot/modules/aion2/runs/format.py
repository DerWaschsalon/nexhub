"""AION-2: Zahlen, Zeiten und Rekordzeilen, wie sie in Posts, Bildern und der Bestenliste stehen."""

from __future__ import annotations

from .records import DpsRecord, RunResult


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


def records_text(result: RunResult) -> str:
    """Kurze Zeilen fürs Feld „🏆 Rekorde“ im Run-Post."""
    lines = [time_line(result)]
    if result.dps_record:
        lines.append(dps_record_line(result.dps_record))
    if result.personal_bests:
        lines.append(f"📈 Persönliche Bestleistung: {', '.join(result.personal_bests)}")
    return "\n".join(lines)


def time_line(result: RunResult) -> str:
    if result.best_before_ms is None:
        return f"🏁 Erste Bestzeit: **{fmt_time(result.fight_ms)}**"
    if result.fight_ms < result.best_before_ms:
        return f"🏁 **Neue Bestzeit!** {fmt_time(result.fight_ms)}, vorher {fmt_time(result.best_before_ms)}"
    return f"Platz {result.place} von {result.runs} Runs · Bestzeit {fmt_time(result.best_before_ms)}"


def dps_record_line(record: DpsRecord) -> str:
    line = f"🥇 **Neuer DPS-Rekord:** {record.player} {fmt_dps(record.dps)}"
    if record.previous_player:
        line += f", vorher {record.previous_player} {fmt_dps(record.previous_dps)}"
    return line
