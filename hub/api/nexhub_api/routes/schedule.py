"""Feste Termine der AION-2-Server (nexproto.termine) für die Seite „Termine“.

    GET /api/public/termine   ohne Login: keine Personendaten, nur der Zeitplan

Gerechnet wird hier; die Seite zählt nur bis zu den gelieferten Zeiten herunter und fragt nach, sobald
ein Termin beginnt oder endet.
"""
from __future__ import annotations

import time

from fastapi import APIRouter
from nexproto.termine import EVENTS, SERVER_ZONE, WEEK_MIN, starts_between, upcoming
from pydantic import BaseModel

router = APIRouter(prefix="/api/public", tags=["öffentlich"])

WEEK_S = WEEK_MIN * 60


class Entry(BaseModel):
    key: str
    name_en: str
    name_de: str
    start: float  # Sekunden seit 1970
    open_until: float | None  # nur solange der Termin offen ist
    place: str


class Planned(BaseModel):
    key: str
    start: float


class Schedule(BaseModel):
    now: float
    server_zone: str  # IANA-Name der Server-Uhr, für die Anzeige „Serverzeit“
    events: list[Entry]
    week: list[Planned]  # Wochentermine der nächsten sieben Tage, nach Beginn


@router.get("/termine")
async def schedule() -> Schedule:
    now = time.time()
    events = [Entry(key=event.key, name_en=event.name_en, name_de=event.name_de, start=start,
                    open_until=open_until, place=event.place)
              for event, start, open_until in upcoming(now)]
    week = [Planned(key=event.key, start=start)
            for event in EVENTS if event.weekdays
            for start in starts_between(event, now, now + WEEK_S)]
    return Schedule(now=now, server_zone=SERVER_ZONE.key, events=events, week=sorted(week, key=lambda p: p.start))
