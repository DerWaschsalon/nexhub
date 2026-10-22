"""Charakterprofile: Momentaufnahmen von der AION-2-Website.

`fill` füllt eine Momentaufnahme (models.Snapshot) – für Mitspieler eines Runs wie für die Armory
(armory.py), damit Abruf und Fehlerbehandlung nur einmal existieren.

Mitspieler: beim Upload legt `create` je Spieler eine Zeile `offen` an (maskierte Namen gleich als
`name_maskiert`), danach füllt `Fetcher.run` sie im Hintergrund. Startet der Hub neu, holt
`Fetcher.resume` liegengebliebene Zeilen nach.
"""
from __future__ import annotations

import logging
from datetime import UTC, datetime

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker
from sqlalchemy.orm.exc import StaleDataError

from nexproto import NexLog
from nexproto.nexlog import JOB_CLASSES, player_name

from .aion2 import LANGS, NC, NCError, NotFound, combat_power, item_level, localized
from .models import RunCharacter, Snapshot

log = logging.getLogger(__name__)

# Wie oft `run` nachsieht, ob während des Abrufs Zeilen wieder geöffnet wurden (refresh)
PASSES = 5


def _server(value: object) -> int:
    """serverId aus der Kampfdatei; das Feld prüft das Modell nicht (extra="allow"), also vorsichtig."""
    if isinstance(value, str) and value.isdigit():
        value = int(value)
    return value if isinstance(value, int) and not isinstance(value, bool) and 0 <= value < 2**31 else 0


def players_of(nexlog: NexLog) -> list[tuple[str, str | None, int]]:
    """(Name, Klasse, Server-ID) aller Spieler in den Kämpfen, jeder einmal. A2Tools schreibt die
    Server-ID je Actor (`serverId`, 0 = unbekannt); eine echte ID gewinnt gegen 0."""
    found: dict[str, tuple[str, str | None, int]] = {}
    for fight in nexlog.fights:
        for actor in fight.actors:
            name = player_name(nexlog, actor)
            server = _server((actor.model_extra or {}).get("serverId"))
            if name not in found or (server and not found[name][2]):
                found[name] = (name, JOB_CLASSES.get(actor.jobId), server)
    return list(found.values())


async def create(db: AsyncSession, run_id: int, nexlog: NexLog) -> None:
    for name, cls, server in players_of(nexlog):
        db.add(RunCharacter(run_id=run_id, name=name[:64], cls=cls, server_id=server,
                            status="name_maskiert" if "*" in name else "offen"))
    await db.commit()


async def fill(nc: NC, row: Snapshot, where: str, items: bool = False) -> None:
    """Holt die Momentaufnahme (beide Sprachen, mit `items` auch die Werte je Gegenstand) und setzt
    Status, Daten und Kennzahlen. Wirft nie: ein Fehler landet als Status `fehler`/`nicht_gefunden`
    in der Zeile, die bisherigen Daten bleiben. Mit bekannter Charakter-ID entfällt die Suche."""
    try:
        cid = row.nc_character_id or await nc.find(row.name, row.server_id)
        data = await nc.snapshots(row.server_id, cid, items)
    except NotFound as e:
        row.status, row.error = "nicht_gefunden", str(e)[:200]
    except NCError as e:
        row.status, row.error = "fehler", str(e)[:200]
        log.warning("Charakter %s (%s): %s", row.name, where, e)
    except Exception as e:  # unerwartete Antwort von NC: nie in „offen“ hängen bleiben
        row.status, row.error = "fehler", f"Format unbekannt: {type(e).__name__}"
        log.exception("Charakter %s (%s): unerwartete Antwort", row.name, where)
    else:
        row.status, row.error, row.nc_character_id, row.data = "ok", None, cid, data
        row.combat_power = combat_power(data)
        row.item_level = item_level(data)
    row.fetched_at = datetime.now(UTC)


def has_item_ids(data: dict | None) -> bool:
    """Ab FORMAT 2 merkt sich die Momentaufnahme die Gegenstands-IDs; nur dann lassen sich Werte nachladen."""
    if not data or not data.get("v"):
        return False
    return any(item.get("id") for item in localized(data).get("equipment", []))


async def load_details(nc: NC, row: Snapshot, where: str) -> None:
    """Werte je Gegenstand zu einer gespeicherten Momentaufnahme nachladen (Knopf bei Run-Mitspielern).
    Geholt wird für genau die gespeicherten Gegenstände; trägt der Charakter einen nicht mehr, bleibt
    er ohne Werte. Stand und Ergebnis stehen in data["details"]. Wirft nie."""
    data = dict(row.data or {})
    try:
        for lang in LANGS:
            snap = data.get(lang) or {}
            equipment = []
            for item in snap.get("equipment", []):
                detail = await nc.item(row.server_id, row.nc_character_id, lang, item)
                equipment.append({**item, "detail": detail})
            data[lang] = {**snap, "equipment": equipment}
        data["details"] = {"state": "ok"}
    except NCError as e:  # NC nicht erreichbar: der Knopf darf es noch einmal versuchen
        data["details"] = {"state": "fehler", "error": str(e)[:200]}
        log.warning("Item-Werte %s (%s): %s", row.name, where, e)
    except Exception:
        data["details"] = {"state": "fehler", "error": "Format unbekannt"}
        log.exception("Item-Werte %s (%s): unerwartete Antwort", row.name, where)
    data["details"]["at"] = datetime.now(UTC).isoformat()
    row.data = data  # neu zuweisen, sonst merkt SQLAlchemy die Änderung im JSON nicht


class Fetcher:
    """Füllt offene Zeilen, einen Run nach dem anderen; läuft ein Run schon, kommt er nicht doppelt."""

    def __init__(self, sessionmaker: async_sessionmaker[AsyncSession], nc: NC) -> None:
        self.sessionmaker, self.nc = sessionmaker, nc
        self.running: set[int] = set()
        self.loading: set[int] = set()  # Mitspieler, deren Item-Werte gerade nachgeladen werden

    async def details(self, char_id: int) -> None:
        if char_id in self.loading:
            return
        self.loading.add(char_id)
        try:
            async with self.sessionmaker() as db:
                row = await db.get(RunCharacter, char_id)
                if row is None:  # Run inzwischen gelöscht
                    return
                await load_details(self.nc, row, f"Run {row.run_id}")
                try:
                    await db.commit()
                except StaleDataError:
                    await db.rollback()
        finally:
            self.loading.discard(char_id)

    async def run(self, run_id: int) -> None:
        if run_id in self.running:
            return
        self.running.add(run_id)
        try:
            async with self.sessionmaker() as db:
                # Mehrere Durchgänge: refresh kann Zeilen wieder öffnen, während dieser Abruf läuft
                for _ in range(PASSES):
                    pending = (await db.scalars(select(RunCharacter).where(
                        RunCharacter.run_id == run_id, RunCharacter.status == "offen"))).all()
                    if not pending:
                        return
                    for row in pending:
                        await fill(self.nc, row, f"Run {run_id}")
                        try:
                            await db.commit()
                        except StaleDataError:
                            await db.rollback()  # Run inzwischen gelöscht
                            return
        finally:
            self.running.discard(run_id)

    async def resume(self) -> None:
        async with self.sessionmaker() as db:
            run_ids = (await db.scalars(select(RunCharacter.run_id).where(
                RunCharacter.status == "offen").distinct())).all()
        for run_id in run_ids:
            try:
                await self.run(run_id)
            except Exception:  # ein kaputter Run hält die anderen nicht auf
                log.exception("Charakterprofile für Run %d nicht nachgeholt", run_id)
