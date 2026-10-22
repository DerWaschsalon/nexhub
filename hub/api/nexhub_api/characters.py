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

from .aion2 import NC, NCError, NotFound, item_level
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


async def fill(nc: NC, row: Snapshot, where: str) -> None:
    """Holt die Momentaufnahme und setzt Status, Daten und Kennzahlen. Wirft nie: ein Fehler landet
    als Status `fehler`/`nicht_gefunden` in der Zeile. Mit bekannter Charakter-ID entfällt die Suche."""
    try:
        cid = row.nc_character_id or await nc.find(row.name, row.server_id)
        data = await nc.snapshot(row.server_id, cid)
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
        row.combat_power = (data.get("profile") or {}).get("combat_power")
        row.item_level = item_level(data)
    row.fetched_at = datetime.now(UTC)


class Fetcher:
    """Füllt offene Zeilen, einen Run nach dem anderen; läuft ein Run schon, kommt er nicht doppelt."""

    def __init__(self, sessionmaker: async_sessionmaker[AsyncSession], nc: NC) -> None:
        self.sessionmaker, self.nc = sessionmaker, nc
        self.running: set[int] = set()

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
