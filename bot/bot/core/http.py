"""Gemeinsame Grenzen für Abrufe des Bots nach außen (GitHub, YouTube, Musikquellen)."""
from __future__ import annotations

import aiohttp

# Ohne eigene Grenze wartet aiohttp bis zu 5 Minuten, so lange hinge das Modul an einem toten Server.
# Grenzen je Schritt statt insgesamt: eine lange, aber laufende Antwort wird nicht abgebrochen.
HTTP_TIMEOUT = aiohttp.ClientTimeout(total=None, sock_connect=10, sock_read=30)
