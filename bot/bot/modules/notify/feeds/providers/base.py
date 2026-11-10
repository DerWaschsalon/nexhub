"""Gemeinsame Schnittstelle für Benachrichtigungs-Provider.

Ein Provider (siehe `github.py` für das erste Beispiel) bekommt Quelle, gewählte Ereignisse,
Filter und den zuletzt gespeicherten Zustand, und liefert neue Meldungen plus aktualisierten
Zustand zurück. Der Discord-Teil (`modules/notify/feeds/wizard.py`) kennt nur diese Schnittstelle,
nichts GitHub-Spezifisches — ein neuer Dienst (YouTube, Twitch, RSS, …) muss nur `Provider`
implementieren und sich in `PROVIDERS` eintragen.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

import discord


@dataclass
class Notification:
    """Eine einzelne Meldung, bereit fürs Posten."""

    event: str  # Schlüssel aus Provider.events, nur für Anzeige/Logging
    embed: discord.Embed


class ProviderError(Exception):
    """Nutzerverständlicher Fehlertext (ungültige Quelle, nicht erreichbar, Rate-Limit, …)."""


class Provider:
    key: str = ""
    label: str = ""
    events: dict[str, str] = {}  # Schlüssel -> Anzeigename, für Mehrfachauswahl + Zusammenfassung
    source_label: str = "Quelle"
    source_example: str = ""
    source_help: str = ""
    # Zusätzliche Filter fürs Formular im NexHub (hubpages.Field, Schlüssel wie in `filters`)
    filter_fields: tuple[Any, ...] = ()

    def filters_from(self, values: dict[str, Any]) -> dict[str, Any]:
        """Werte der `filter_fields` aus dem Hub → gespeicherte `filters` (leere fallen weg)."""
        return {k: v for k, v in values.items() if v not in (None, "", [])}

    async def validate_source(self, source: str) -> str:
        """Wirft `ProviderError` bei ungültiger Eingabe, gibt sonst die normalisierte Quelle zurück."""
        raise NotImplementedError

    async def poll(
        self, source: str, events: list[str], filters: dict[str, Any], state: dict[str, Any], *, baseline: bool
    ) -> tuple[list[Notification], dict[str, Any]]:
        """Neue Meldungen seit `state`, plus aktualisierter Zustand zum Speichern.

        `baseline=True` beim allerersten Abruf eines Feeds: nur den Zustand füllen, nichts
        melden — sonst würde jeder schon bestehende Eintrag beim Einrichten als „neu" gemeldet.
        """
        raise NotImplementedError

    async def test_notification(self, source: str, events: list[str]) -> Notification:
        """Für den Test-Button: eine Beispiel-Meldung, ohne den gespeicherten Zustand zu ändern."""
        raise NotImplementedError

    async def close(self) -> None:
        pass
