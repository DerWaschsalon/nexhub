"""HTTP-Absprachen zwischen NexBoard-Daemon, Hub und Bot: API-Stand und Anfrage-Kennung.

API-Stand: Der Daemon läuft auf fremden PCs und ist oft älter als der Hub. Er schickt `HUB_API` in
`API_HEADER` mit. Ändert sich ein Geräte-Endpunkt des Hubs so, dass ältere Daemons ihn falsch verstehen,
wird `HUB_API` erhöht; der Hub antwortet älteren Daemons dann mit 426 und „bitte aktualisieren“, statt
dass sie still scheitern.

Anfrage-Kennung: Der Daemon vergibt je Upload eine Kennung und schickt sie in `REQUEST_ID_HEADER`. Hub
und Bot schreiben sie in jede Logzeile dieser Anfrage und reichen sie weiter. So lässt sich ein Run in
den Logs aller drei Teile finden.
"""
from __future__ import annotations

import logging
import re
import uuid
from contextvars import ContextVar

HUB_API = 1
API_HEADER = "X-NexBoard-Api"
REQUEST_ID_HEADER = "X-Request-ID"
# Ohne Kopfzeile ist es ein Daemon von vor dieser Absprache; der spricht Stand 1
HUB_API_WITHOUT_HEADER = 1

REQUEST_ID_LEN = 12
# Fremde Kennungen nur übernehmen, wenn sie harmlos sind (landen ungefiltert im Log)
_REQUEST_ID_PATTERN = re.compile(r"^[A-Za-z0-9-]{1,64}$")

request_id: ContextVar[str] = ContextVar("request_id", default="-")


def new_request_id() -> str:
    return uuid.uuid4().hex[:REQUEST_ID_LEN]


def accept_request_id(value: str | None) -> str:
    """Mitgeschickte Kennung übernehmen, sonst eine neue vergeben."""
    if value and _REQUEST_ID_PATTERN.match(value):
        return value
    return new_request_id()


def client_api(value: str | None) -> int:
    """API-Stand aus der Kopfzeile; unlesbar zählt wie zu alt."""
    if value is None:
        return HUB_API_WITHOUT_HEADER
    try:
        return int(value)
    except ValueError:
        return 0


class RequestIdFilter(logging.Filter):
    """Hängt die Kennung der laufenden Anfrage an jede Logzeile (Feld `request_id` im Format)."""

    def filter(self, record: logging.LogRecord) -> bool:
        record.request_id = request_id.get()
        return True


def log_request_ids() -> None:
    """Kennung in alle Handler des Root-Loggers einbauen; nach logging.basicConfig aufrufen."""
    for handler in logging.getLogger().handlers:
        handler.addFilter(RequestIdFilter())
