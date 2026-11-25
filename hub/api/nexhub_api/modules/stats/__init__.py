"""Modul Statistik: Zahlen für Admins über die anderen Module."""
from __future__ import annotations

from ...module import ApiModule
from . import routes

MODULE = ApiModule("stats", (routes.router,), requires=("logs", "armory", "bis"))
