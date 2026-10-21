"""Logging: einheitliches Format und ein Zugriffslog ohne Geheimnisse."""
from __future__ import annotations

import logging

# Pfade, deren Query Geheimnisse trägt: beim Discord-Rücksprung stehen dort code und state
SECRET_QUERY_PATHS = ("/api/auth/callback",)


class HideSecretQuery(logging.Filter):
    """Kürzt Zugriffslog-Zeilen von uvicorn auf den Pfad, wenn die Query Geheimnisse trägt.

    uvicorn übergibt die Zeile als (Client, Methode, Pfad mit Query, HTTP-Version, Status).
    """

    def filter(self, record: logging.LogRecord) -> bool:
        args = record.args
        if isinstance(args, tuple) and len(args) == 5 and isinstance(args[2], str):
            path, _, query = args[2].partition("?")
            if query and path in SECRET_QUERY_PATHS:
                record.args = (args[0], args[1], f"{path}?…", args[3], args[4])
        return True


def setup() -> None:
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s: %(message)s")
    # httpx meldet jede Anfrage an Discord; das reicht als Warnung bei Fehlern
    logging.getLogger("httpx").setLevel(logging.WARNING)
