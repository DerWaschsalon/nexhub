"""Fehlerformat aller HTTP-Schnittstellen: {"error": "<lesbarer Grund>"} mit passendem Status."""
from __future__ import annotations

from pydantic import ValidationError


class ApiError(Exception):
    def __init__(self, status: int, message: str) -> None:
        super().__init__(message)
        self.status = status
        self.message = message

    def body(self) -> dict[str, str]:
        return {"error": self.message}


def invalid(e: ValidationError) -> ApiError:
    """Prüffehler einer Eingabe als 422 mit den Feldern, die nicht passen."""
    parts = [f"{'.'.join(map(str, err['loc'])) or 'Eingabe'}: {err['msg']}" for err in e.errors()]
    return ApiError(422, "; ".join(parts))
