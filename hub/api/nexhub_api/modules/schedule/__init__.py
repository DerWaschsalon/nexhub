"""Modul Termine: die festen Termine der Server."""
from __future__ import annotations

from ...module import ApiModule
from . import routes

MODULE = ApiModule("schedule", (routes.router,))
