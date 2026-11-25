"""Tagesreihen für die Admin-Statistik. Rein: aus Zeitstempeln wird „wie viele je Tag“."""
from __future__ import annotations

from collections import Counter
from datetime import date, datetime, timedelta


def last_days(today: date, days: int) -> list[date]:
    """Die letzten `days` Tage bis heute, der älteste zuerst."""
    return [today - timedelta(days=back) for back in range(days - 1, -1, -1)]


def per_day(stamps: list[datetime], days: list[date]) -> list[int]:
    """Wie viele Zeitstempel auf jeden der Tage fallen (in der Zeitzone der Stempel, hier UTC)."""
    counted = Counter(stamp.date() for stamp in stamps)
    return [counted.get(day, 0) for day in days]
