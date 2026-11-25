"""Modul Beute: was Bosse fallen lassen, gezählt aus den Runs."""
from __future__ import annotations

from ...module import ApiModule
from . import routes

MODULE = ApiModule("loot", (routes.router,), requires=("logs",))
