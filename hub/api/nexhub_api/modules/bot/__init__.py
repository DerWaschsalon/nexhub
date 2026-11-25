"""Modul Bot: reicht die Verwaltung des Discord-Bots an ihn durch."""
from __future__ import annotations

from ...module import ApiModule
from . import routes

MODULE = ApiModule("bot", (routes.router,))
