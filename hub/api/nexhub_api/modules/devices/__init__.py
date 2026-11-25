"""Modul Geräte: NexBoards mit dem Konto koppeln."""
from __future__ import annotations

from ...module import ApiModule
from . import routes

MODULE = ApiModule("devices", (routes.router,))
