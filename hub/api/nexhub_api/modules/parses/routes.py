"""Parses je Run (Routen folgen)."""
from __future__ import annotations

from fastapi import APIRouter

router = APIRouter(prefix="/api/parses", tags=["runs"])
