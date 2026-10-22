"""Build-Check: ein Armory-Charakter gegen die besten Spieler seiner Klasse, nur auf Klick.

Ablauf: Rangliste von Abyss Logs (abysslogs.py) → Gruppe mit ähnlicher Kampfkraft → Server über die
NC-Suche (die Rangliste nennt keinen) → Profile mit Gegenständen → Auswertung (evaluation.py).
Gespeichert wird nur das Ergebnis, keine Namen und keine Profile der Top-Spieler.
"""
from __future__ import annotations

import asyncio
import logging
from datetime import UTC, datetime, timedelta

import httpx
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from .abysslogs import AbyssError, abyss_class, leaderboard, pick_group, top_bosses
from .aion2 import NCError, NotFound, combat_power, localized
from .armory import Armory
from .evaluation import evaluate
from .models import BuildCheck, Character

log = logging.getLogger(__name__)

GROUP = 15
MIN_GROUP = 5
# Profile gleichzeitig: eines mit Gegenständen braucht rund 40 Anfragen (etwa eine Minute), einzeln
# dauerte ein Check eine Viertelstunde. Vier zugleich halten die Last bei NC noch klein.
PARALLEL = 4
REGION = "eu"
FRESH = timedelta(minutes=10)  # ältere eigene Momentaufnahme vorher neu abrufen
STALE = timedelta(minutes=15)  # länger „läuft“ heißt: ein Neustart hat den Lauf abgebrochen


class CheckError(Exception):
    pass


def aware(when: datetime) -> datetime:
    """SQLite (Tests) gibt Zeitpunkte ohne Zeitzone zurück; gespeichert wird immer UTC."""
    return when.replace(tzinfo=when.tzinfo or UTC)


class BuildChecker:
    """Führt Build-Checks im Hintergrund aus; derselbe Charakter läuft nie doppelt."""

    def __init__(self, sessionmaker: async_sessionmaker[AsyncSession], armory: Armory, http: httpx.AsyncClient) -> None:
        self.sessionmaker, self.armory, self.nc, self.http = sessionmaker, armory, armory.nc, http
        self.running: set[int] = set()

    async def run(self, character_id: int) -> None:
        """Wirft nie: Fehler landen als Status `fehler`, das vorige Ergebnis bleibt."""
        if character_id in self.running:
            return
        self.running.add(character_id)
        try:
            await self._refresh_own(character_id)
            async with self.sessionmaker() as db:
                check = await db.scalar(select(BuildCheck).where(BuildCheck.character_id == character_id))
                row = await db.get(Character, character_id)
                if check is None or row is None:  # inzwischen ausgetragen
                    return
                try:
                    profiles = await self._group(db, row, check)
                    if len(profiles) < MIN_GROUP:
                        raise CheckError(f"Zu wenige Vergleichsspieler ({len(profiles)} von mindestens {MIN_GROUP})")
                    check.result = evaluate(localized(row.data or {}, "en"), profiles)
                    check.status, check.error = "fertig", None
                except (CheckError, AbyssError, NCError) as e:
                    check.status, check.error = "fehler", str(e)[:200]
                except Exception:  # unerwartete Antwort: nie in „läuft“ hängen bleiben
                    log.exception("Build-Check %d: unerwarteter Fehler", character_id)
                    check.status, check.error = "fehler", "Unerwarteter Fehler beim Build-Check"
                check.finished_at = datetime.now(UTC)
                await db.commit()
        finally:
            self.running.discard(character_id)

    async def _refresh_own(self, character_id: int) -> None:
        async with self.sessionmaker() as db:
            row = await db.get(Character, character_id)
            stale = row is not None and (row.fetched_at is None or datetime.now(UTC) - aware(row.fetched_at) > FRESH)
        if stale:
            await self.armory.refresh(character_id)

    async def _own_class(self, row: Character) -> str:
        """Klasse wie im Hub („ranger“). Armory-Charaktere speichern keine; die Suche nennt sie über die pcId."""
        for hit in await self.nc.search(row.name, REGION):
            if hit["server_id"] == row.server_id and hit["character_id"] == row.nc_character_id and hit["cls"]:
                return hit["cls"]
        raise CheckError("Klasse des Charakters nicht ermittelbar")

    async def _group(self, db: AsyncSession, row: Character, check: BuildCheck) -> list[dict]:
        cls = await self._own_class(row)
        entries = [e for boss in await top_bosses(self.http)
                   for e in await leaderboard(self.http, abyss_class(cls), boss)]
        candidates = pick_group(entries, row.combat_power or 0)
        profiles: list[dict] = []
        for start in range(0, len(candidates), PARALLEL):
            if len(profiles) >= GROUP:
                break
            batch = await asyncio.gather(*(self._profile(e, cls) for e in candidates[start:start + PARALLEL]))
            profiles += [p for p in batch if p is not None][:GROUP - len(profiles)]
            check.progress = len(profiles)
            await db.commit()
        return profiles

    async def _profile(self, entry: dict, cls: str) -> dict | None:
        """Profil zu einem Namen der Rangliste. Gibt es den Namen auf mehreren Servern, gewinnt die
        Kampfkraft, die der Rangliste am nächsten liegt. Nicht auffindbar: None, der nächste rückt nach."""
        name = entry["playerName"]
        try:
            hits = [h for h in await self.nc.search(name, REGION, cls) if h["name"].casefold() == name.casefold()]
            if len(hits) > 1:
                cp = entry.get("combatPower") or 0
                profiles = [(h, await self.nc.snapshot(h["server_id"], h["character_id"], "en")) for h in hits]
                hits = [min(profiles, key=lambda hp: abs((combat_power(hp[1]) or 0) - cp))[0]]
            if not hits:
                return None
            return await self.nc.snapshot(hits[0]["server_id"], hits[0]["character_id"], "en", items=True)
        except (NotFound, NCError) as e:
            log.info("Build-Check: %s übersprungen (%s)", name, e)
            return None
