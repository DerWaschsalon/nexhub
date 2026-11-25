"""Modul Feedback: Wünsche und Fehler mit Stimmen."""
from __future__ import annotations

from ...module import ApiModule
from . import routes

MODULE = ApiModule("feedback", (routes.router,))
