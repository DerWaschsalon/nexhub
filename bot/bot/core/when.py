"""Zeitangaben für Erinnerungen: relativ („2h“, „30m“, „1d2h“) oder absolut („18:30“ heute oder morgen,
„24.12. 18:00“ mit optionalem Jahr), in deutscher Zeit."""

from __future__ import annotations

import re
from datetime import datetime, timedelta

from bot.core.clock import TZ
from bot.errors import UserError

RELATIVE_RE = re.compile(r"^(?:(\d+)d)?(?:(\d+)h)?(?:(\d+)m)?$")
TIME_RE = re.compile(r"^(\d{1,2}):(\d{2})$")
DATE_TIME_RE = re.compile(r"^(\d{1,2})\.(\d{1,2})\.(?:(\d{4}))?\s+(\d{1,2}):(\d{2})$")
EXAMPLES = "`2h`, `30m`, `1d2h`, `18:30`, `24.12. 18:00`"


def parse_when(text: str, now: datetime) -> datetime:
    text = text.strip()
    for parse in (relative, time_of_day, date_and_time):
        when = parse(text, now)
        if when is not None:
            return when
    raise UserError(f"„{text}“ verstehe ich nicht. Beispiele: {EXAMPLES}.")


def relative(text: str, now: datetime) -> datetime | None:
    match = RELATIVE_RE.match(text)
    if not match or not any(match.groups()):
        return None
    days, hours, minutes = (int(g) if g else 0 for g in match.groups())
    return now + timedelta(days=days, hours=hours, minutes=minutes)


def time_of_day(text: str, now: datetime) -> datetime | None:
    """„18:30“: heute, oder morgen, wenn die Uhrzeit heute schon vorbei ist."""
    match = TIME_RE.match(text)
    if not match:
        return None
    when = now.replace(hour=int(match.group(1)), minute=int(match.group(2)), second=0, microsecond=0)
    return when if when > now else when + timedelta(days=1)


def date_and_time(text: str, now: datetime) -> datetime | None:
    """„24.12. 18:00“: ohne Jahr das nächste Mal, an dem dieser Tag kommt."""
    match = DATE_TIME_RE.match(text)
    if not match:
        return None
    day, month, year, hour, minute = match.groups()
    target_year = int(year) if year else now.year
    try:
        when = datetime(target_year, int(month), int(day), int(hour), int(minute), tzinfo=TZ)
    except ValueError:
        raise UserError(f"„{text}“ ist kein gültiges Datum.") from None
    if not year and when <= now:
        when = when.replace(year=target_year + 1)
    return when
