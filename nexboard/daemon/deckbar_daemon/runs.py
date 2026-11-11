"""AION-2-Dungeon-Runs (Beobachten und Posten; Daten in run_model.py, Bild in run_image.py): nach jedem Run ein PNG mit der Schadensaufteilung pro Boss nach Discord.

Quelle ist nicht der Live-Stream (dps.py), sondern die Kampf-History im Format des A2Tools-Meters,
geschrieben von deckbar-capture (Quelle `capture`) oder vom Meter selbst:
Für jeden Bosskampf entsteht `history/<id>.json`, mit Dungeon, Boss, maximalen HP und
dem Schaden jeder Fähigkeit pro Spieler. Die Datei entsteht schon während des Kampfs und
wird laufend neu geschrieben – sie wird deshalb bei jeder Änderung neu gelesen, und ein
beendeter Run geht erst raus, wenn seine Dateien `SETTLE_RUN_S` lang ruhen. Aufeinanderfolgende Kämpfe im selben Dungeon
ergeben einen Run. Er endet,
  - sobald der Endboss liegt: laut `END_BOSSES` (recherchiert, englische Namen aus den
    Meter-Daten), sonst der Boss mit den meisten HP, den es in diesem Dungeon in früheren
    Runs schon gab – im ersten Run eines nicht gelisteten Dungeons ist er also unbekannt,
  - wenn der nächste Kampf in einem anderen Dungeon stattfindet oder ein in diesem Run
    schon besiegter Boss wieder auftaucht,
  - oder nach `idle_minutes` ohne neuen Bosskampf.
Gepostet wird jeder Run mit mindestens einem besiegten Boss, per Discord-Webhook.

Das Meter speichert fremde Namen maskiert („Mo***n“: zwei Zeichen vorn, eins hinten), der
Live-Stream (State `dps`) zeigt sie aber voll. Die NexBoard merkt sich die vollen Namen
(Schlüssel „Maske|Klasse“, in runs-state.json); von Hand in der Web-UI Eingetragenes
(`names` in aion2.runs.yaml) hat Vorrang.
"""
from __future__ import annotations

import asyncio
import json
import logging
import os
import re
import time
from datetime import datetime
from pathlib import Path
from typing import Awaitable, Callable

import aiohttp
from nexcore.settings import ADVANCED, HIDDEN, SECRET, SettingsStore
from pydantic import Field, field_validator

from .config import _atomic_write, _Strict
from .run_image import fmt_time, render_run, run_image
from .run_model import (
    Fight,
    Run,
    RunTracker,
    a2tools_dir,
    char_key,
    dungeon_name,
    is_end_boss,
    load_fight,
    mask,
)

log = logging.getLogger(__name__)

SETTINGS_FILE = "aion2.runs.yaml"  # im Konfig-Ordner, benannt nach dem Modul
SETTINGS_HEADER = "AION-2-Dungeon-Runs nach Discord – wird von der Web-UI überschrieben."

POLL_S = 5
# Datei erst lesen, wenn das Meter sie so lange nicht mehr angefasst hat
SETTLE_S = 2
# Beendeten Run erst posten, wenn keine seiner Dateien sich so lange geändert hat
SETTLE_RUN_S = 20
# Beim Start nachgeholte Runs nur posten, wenn sie so frisch sind
LATE_POST_S = 3600
# gelernte Namen (runs-state.json); Weltbosse bringen schnell Dutzende Fremde mit
MAX_LEARNED = 1000
# so lange bleiben Kämpfe im Speicher (Mitspielerliste, Vorschau); beim Start werden nur so alte
# Dateien gelesen, die Endbosse aus älteren stehen in runs-state.json
KEEP_DAYS = 30
# Aufräumen alter History-Dateien (Einstellung history_days) höchstens so oft
CLEANUP_S = 6 * 3600
WEBHOOK_RE = re.compile(r"^https://(?:(?:ptb|canary)\.)?discord(?:app)?\.com/api/webhooks/\d+/[\w-]+$")


class RunSettings(_Strict):
    enabled: bool = Field(False, title="Bild posten", description="Nach jedem Run per Webhook in einen Discord-Kanal")
    webhook: str = Field("", max_length=200, title="Discord-Webhook",
                         description="Kanal bearbeiten → Integrationen → Webhooks", json_schema_extra=SECRET)
    idle_minutes: int = Field(15, ge=2, le=120, title="Run vorbei nach (min ohne Boss)")
    # „Mo***n|ranger“ → echter Name; eigene Oberfläche (Namen der Mitspieler)
    names: dict[str, str] = Field(default_factory=dict, max_length=200, json_schema_extra=HIDDEN)
    history_days: int = Field(0, ge=0, le=3650, title="History aufbewahren (Tage)",
                              description="0 = alles behalten. Löscht ältere Kämpfe aus dem eigenen Mitschnitt "
                                          "(~2,5 MB pro Spieltag), nie die des A2Tools-Meters.",
                              json_schema_extra=ADVANCED)

    @field_validator("webhook")
    @classmethod
    def _webhook(cls, v: str) -> str:
        v = v.strip()
        if v and not WEBHOOK_RE.match(v):
            raise ValueError("keine Discord-Webhook-URL (https://discord.com/api/webhooks/…)")
        return v

    @field_validator("names")
    @classmethod
    def _names(cls, v: dict[str, str]) -> dict[str, str]:
        out = {}
        for k, name in v.items():
            name = name.strip()[:24]
            if name and len(k) <= 48:
                out[k] = name
        return out


def run_message(run: Run) -> str:
    bosses = run.bosses()
    fight_ms = sum(b.duration_ms for b in bosses)
    return (f"**{run.name}** – {run.kills}/{len(bosses)} {'Boss' if len(bosses) == 1 else 'Bosse'} besiegt, "
            f"Kampfzeit {fmt_time(fight_ms)} ({datetime.fromtimestamp(run.start_ms / 1000):%H:%M}–"
            f"{datetime.fromtimestamp(run.end_ms / 1000):%H:%M})")


async def post_discord(session: aiohttp.ClientSession, webhook: str, text: str, png: bytes, filename: str) -> None:
    """PNG + Text an einen Discord-Webhook; wartet einmal, falls Discord bremst (429)."""
    payload = {"content": text, "username": "NexBoard", "allowed_mentions": {"parse": []},
               "attachments": [{"id": 0, "filename": filename}]}
    for attempt in range(2):
        form = aiohttp.FormData()
        form.add_field("payload_json", json.dumps(payload), content_type="application/json")
        form.add_field("files[0]", png, filename=filename, content_type="image/webp")
        async with session.post(webhook, data=form) as resp:
            if resp.status == 429 and attempt == 0:
                retry = float((await resp.json(content_type=None) or {}).get("retry_after", 2))
                await asyncio.sleep(min(retry, 30))
                continue
            if resp.status >= 300:
                body = (await resp.text())[:200]
                raise RuntimeError(f"Discord antwortet {resp.status}: {body}")
            return


# ---------------------------------------------------------------- Dienst
class DungeonRuns:
    def __init__(self, config_dir: Path) -> None:
        self.store = SettingsStore(config_dir / SETTINGS_FILE, RunSettings, header=SETTINGS_HEADER)
        self.state_path = config_dir / "runs-state.json"
        self.settings = self.store.value
        self.tracker = RunTracker(self.settings.idle_minutes * 60_000)
        self.mtimes: dict[str, float] = {}  # Dateiname → zuletzt gelesene Änderungszeit
        self.fights: dict[str, Fight] = {}  # alle Dungeon-Kämpfe nach id (Mitspielerliste, Vorschau)
        self.pending: list[tuple[Run, float]] = []  # beendet, wartet auf Ruhe in den Dateien
        self.done: set[str] = set()  # Kämpfe aus erledigten Runs – späte Änderungen ignorieren
        self.last_ms, self.learned, known = self._read_state()
        self.full_read = known is None  # Endbosse noch nie gesichert: beim Start alles lesen
        for dungeon, mobs in (known or {}).items():
            for mob, hp in mobs.items():
                self.tracker.known.setdefault(dungeon, {})[mob] = hp
                if is_end_boss(mob):
                    self.tracker.listed.add(dungeon)
        self.last: Run | None = None  # zuletzt beendeter Run (Vorschau, Testpost)
        self.result = ""  # letzter Post: Erfolg oder Fehler, für die Web-UI
        self.listeners: list[Callable[[], Awaitable[None]]] = []
        # Jeder beendete Run mit besiegtem Boss, Namen schon aufgelöst (z. B. NexHub, hub.py)
        self.run_listeners: list[Callable[[Run], Awaitable[None]]] = []
        self._ready = False
        # Wo die History liegt, hängt an der DPS-Quelle (app.py setzt das)
        self.history_dir: Callable[[], Path] = lambda: a2tools_dir() / "history"
        # True = eigener Mitschnitt: gelesen wird nur nach dessen Meldung „fights_saved“ (wake()),
        # statt alle POLL_S den Ordner abzufragen. Das A2Tools-Meter meldet nichts, dort pollen.
        self.event_driven: Callable[[], bool] = lambda: False
        self.own_history: Callable[[], bool] = lambda: False  # darf alte Dateien löschen
        self._dirty = True
        self._unsettled = False
        self._cleaned = 0.0

    # ------------------------------------------------------------ Einstellungen
    def save(self, settings: RunSettings) -> None:
        self.store.save(settings)
        self.settings = settings
        self.tracker.idle_ms = settings.idle_minutes * 60_000

    def info(self) -> dict:
        s = self.settings.model_dump()
        s["webhook"] = "•" * 8 if s["webhook"] else ""  # die URL verlässt den Daemon nicht
        last = None
        if self.last:
            last = {"name": self.last.name, "end": self.last.end_ms, "kills": self.last.kills}
        return {"settings": s, "history": self.history_dir().is_dir(),
                "last_run": last, "result": self.result, "open_run": bool(self.tracker.run),
                "characters": self.characters()}

    def names(self) -> dict[str, str]:
        """Maske|Klasse → echter Name: in der History unmaskiert oder live gesehen; von Hand Eingetragenes zuletzt."""
        full = {p.key: p.name for f in self.fights.values() for p in f.players if "*" not in p.name}
        return {**full, **self.learned, **self.settings.names}

    def characters(self) -> list[dict]:
        """Mitspieler aus den Dungeon-Kämpfen der letzten 30 Tage, häufigste zuerst (für die Namensliste)."""
        names = self.settings.names
        full = self.names()
        seen: dict[str, dict] = {}
        for f in self.fights.values():
            if f.start_ms < (time.time() - 30 * 86400) * 1000:
                continue
            for p in f.players:
                c = seen.setdefault(p.key, {"key": p.key, "mask": mask(p.name), "cls": p.cls, "count": 0, "you": False})
                c["count"] += 1
                c["you"] |= p.you
        out = [c for c in seen.values() if c["count"] >= 2 or c["key"] in names]
        out = sorted(out, key=lambda c: (not c["you"], -c["count"], c["mask"].lower()))[:12]
        for c in out:
            c["name"] = names.get(c["key"], "")
            c["seen"] = full.get(c["key"], "") if c["key"] not in names else ""  # bekannt → Platzhalter
        return out

    def observe(self, value: dict | None) -> None:
        """Live-Stand vom Meter (State `dps`): volle Namen merken, sofern das Meter sie zeigt."""
        if not value:
            return
        new = {}
        for r in value.get("rows") or []:
            name = r.get("name") or ""
            if "*" in name or name.startswith("#") or len(name) < 3:
                continue
            key = char_key(name, r.get("cls"))
            if self.learned.get(key) != name:
                new[key] = name
        if new:
            log.info("Namen aus dem Live-Stream gelernt: %s", ", ".join(new.values()))
            for key in new:
                self.learned.pop(key, None)  # neu Gesehene ans Ende, Älteste fliegen zuerst raus
            self.learned.update(new)
            while len(self.learned) > MAX_LEARNED:
                self.learned.pop(next(iter(self.learned)))
            self._write_state()

    # ------------------------------------------------------------ Zustand über Neustarts
    def _read_state(self) -> tuple[int | None, dict[str, str], dict[int, dict[int, int]] | None]:
        try:
            data = json.loads(self.state_path.read_text())
        except (OSError, ValueError):
            return None, {}, None
        if not isinstance(data, dict):
            return None, {}, None
        try:
            last_ms = int(data["last_ms"])
        except (KeyError, TypeError, ValueError):
            last_ms = None
        learned = data.get("learned")
        # Schlüssel neu bilden, falls sich die Maskenregel geändert hat (Klasse steht hinter dem „|“)
        learned = {char_key(str(v)[:24], str(k).partition("|")[2] or None): str(v)[:24]
                   for k, v in learned.items()} if isinstance(learned, dict) else {}
        known = None
        if isinstance(data.get("known"), dict):
            try:
                known = {int(d): {int(m): int(hp) for m, hp in mobs.items()} for d, mobs in data["known"].items()}
            except (TypeError, ValueError, AttributeError):
                known = None
        return last_ms, learned, known

    def _write_state(self) -> None:
        known = {str(d): {str(m): hp for m, hp in mobs.items()} for d, mobs in self.tracker.known.items()}
        data = {"last_ms": self.last_ms, "learned": self.learned, "known": known}
        _atomic_write(self.state_path, json.dumps(data, ensure_ascii=False, indent=1) + "\n")

    def _scan(self, settle: bool = True, since: float | None = None) -> list[Fight]:
        """Neue und seit dem letzten Lesen geänderte Kämpfe. since: ältere Dateien nur vormerken,
        nicht lesen (Startup; ihre Endbosse stehen in runs-state.json)."""
        hist = self.history_dir()
        now = time.time()
        fights = []
        self._unsettled = False
        try:
            entries = list(os.scandir(hist))
        except OSError:
            return []
        for e in entries:
            if not e.name.endswith(".json"):
                continue
            try:
                mtime = e.stat().st_mtime
            except OSError:
                continue
            if self.mtimes.get(e.name) == mtime:
                continue
            if settle and now - mtime < SETTLE_S:
                self._unsettled = True  # beim nächsten Durchlauf nochmal
                continue
            self.mtimes[e.name] = mtime
            if since is not None and mtime < since:
                continue
            f = load_fight(Path(e.path))
            if f:
                fights.append(f)
                self.fights[f.id] = f
        return sorted(fights, key=lambda f: f.start_ms)

    def _prune(self) -> None:
        """Kämpfe älter als KEEP_DAYS aus dem Speicher; ihre vollen Namen bleiben als gelernte."""
        cutoff = (time.time() - KEEP_DAYS * 86400) * 1000
        old = [f for f in self.fights.values() if f.start_ms < cutoff]
        if not old:
            return
        changed = False
        for f in old:
            del self.fights[f.id]
            for p in f.players:
                if "*" not in p.name and p.key not in self.learned and len(self.learned) < MAX_LEARNED:
                    self.learned[p.key] = p.name
                    changed = True
        if changed:
            self._write_state()

    def _cleanup(self) -> int:
        """History-Dateien des eigenen Mitschnitts löschen, die älter als history_days sind."""
        days = self.settings.history_days
        if not days or not self.own_history():
            return 0
        cutoff = time.time() - days * 86400
        n = 0
        try:
            entries = list(os.scandir(self.history_dir()))
        except OSError:
            return 0
        # Einzeltreffer liegen daneben in hits/<id>.json (deckbar-capture) und gehen mit
        hits_dir = self.history_dir().parent / "hits"
        for e in entries:
            try:
                if e.name.endswith(".json") and e.stat().st_mtime < cutoff:
                    os.unlink(e.path)
                    (hits_dir / e.name).unlink(missing_ok=True)
                    self.mtimes.pop(e.name, None)
                    n += 1
            except OSError:
                continue
        if n:
            log.info("History: %d Kämpfe älter als %d Tage gelöscht", n, days)
        return n

    def wake(self) -> None:
        """Der Mitschnitt hat Kämpfe gespeichert (fights_saved): beim nächsten Durchlauf lesen."""
        self._dirty = True

    def _update_pending(self, f: Fight) -> bool:
        """Neuer Stand eines Kampfs aus einem schon beendeten, noch nicht geposteten Run."""
        for i, (run, _) in enumerate(self.pending):
            for j, old in enumerate(run.fights):
                if old.id == f.id:
                    run.fights[j] = f
                    self.pending[i] = (run, time.monotonic())
                    return True
        return False

    async def start(self) -> list[Run]:
        """Alte Kämpfe einlesen (lernt die Endbosse) und seit dem letzten Run Verpasstes nachholen."""
        since = None if self.full_read else time.time() - KEEP_DAYS * 86400
        fights = await asyncio.to_thread(self._scan, False, since)
        last_ms = self.last_ms
        if last_ms is None:  # erster Start: nichts Altes posten
            self.last_ms = last_ms = int(time.time() * 1000)
            self._write_state()
        closed: list[Run] = []
        for f in fights:
            if f.start_ms <= last_ms:
                self.tracker.learn(f)
                self.done.add(f.id)
            else:
                closed += self.tracker.add(f)
        closed += self.tracker.check_idle(int(time.time() * 1000))
        if self.full_read:  # Endbosse jetzt gesichert, ab dem nächsten Start nur noch KEEP_DAYS lesen
            self.full_read = False
            self._write_state()
        self._prune()
        self._ready = True
        return closed

    async def watch(self) -> None:
        timeout = aiohttp.ClientTimeout(total=30)
        async with aiohttp.ClientSession(timeout=timeout) as session:
            for run in await self.start():
                await self._finish(session, run, late=True)
            while True:
                await asyncio.sleep(POLL_S)
                await self.poll(session)

    async def poll(self, session: aiohttp.ClientSession) -> None:
        closed: list[Run] = []
        fights: list[Fight] = []
        if self._dirty or not self.event_driven():
            self._dirty = False
            fights = await asyncio.to_thread(self._scan)
            self._dirty = self._unsettled  # gerade noch geschriebene Dateien beim nächsten Mal
            self._prune()
        if time.monotonic() - self._cleaned > CLEANUP_S:
            self._cleaned = time.monotonic()
            await asyncio.to_thread(self._cleanup)
        for f in fights:
            log.info("Bosskampf: %s – %s (%s, %s)", dungeon_name(f.dungeon), f.boss,
                     fmt_time(f.duration_ms), "besiegt" if f.killed else "läuft/nicht besiegt")
            if f.id in self.done or self._update_pending(f):
                continue
            closed += self.tracker.add(f)
        closed += self.tracker.check_idle(int(time.time() * 1000))
        now = time.monotonic()
        self.pending += [(run, now) for run in closed]
        for entry in list(self.pending):
            if now - entry[1] >= SETTLE_RUN_S:
                self.pending.remove(entry)
                await self._finish(session, entry[0])

    async def _finish(self, session: aiohttp.ClientSession, run: Run, late: bool = False) -> None:
        self.done |= {f.id for f in run.fights}
        self.last_ms = run.end_ms
        self._write_state()
        log.info("Run beendet: %s, %d Kämpfe, %d Bosse besiegt%s", run.name, len(run.fights), run.kills,
                 " (Endboss)" if run.complete else "")
        if not run.kills:
            return
        self.last = run
        if late and time.time() * 1000 - run.end_ms > LATE_POST_S * 1000:
            await self._notify()
            return
        if self.settings.enabled and self.settings.webhook:
            await self.post(session, run)
        run.rename(self.names())
        for fn in self.run_listeners:
            try:
                await fn(run)
            except Exception:  # ein Zuhörer (Netz) darf das Auswerten nicht anhalten
                log.exception("Run-Zuhörer")
        await self._notify()

    async def post(self, session: aiohttp.ClientSession, run: Run) -> bool:
        run.rename(self.names())
        try:
            png = await run_image(run)
            name = f"run-{datetime.fromtimestamp(run.start_ms / 1000):%Y%m%d-%H%M}.webp"
            await post_discord(session, self.settings.webhook, run_message(run), png, name)
        except (aiohttp.ClientError, TimeoutError, RuntimeError, OSError) as e:
            self.result = f"Fehler beim Posten: {e}"
            log.warning("Discord: %s", e)
            return False
        self.result = f"gepostet: {run.name}, {datetime.fromtimestamp(run.end_ms / 1000):%d.%m. %H:%M}"
        log.info("Discord: %s", self.result)
        return True

    def latest_run(self) -> Run | None:
        """Zuletzt beendeter Run – oder, falls seit dem Start keiner endete, der letzte aus der History."""
        run = self.last or self._last_from_history()
        if run:
            run.rename(self.names())
        return run

    def _last_from_history(self) -> Run | None:
        fights = list(self.fights.values()) or [
            f for f in (load_fight(p) for p in self.history_dir().glob("*.json")) if f]
        tracker = RunTracker(self.settings.idle_minutes * 60_000)
        runs: list[Run] = []
        for f in sorted(fights, key=lambda f: f.start_ms):
            runs += tracker.add(f)
        runs += tracker.check_idle(int(time.time() * 1000))  # der laufende Run zählt noch nicht
        runs = [r for r in runs if r.kills]
        return runs[-1] if runs else None

    async def _notify(self) -> None:
        for fn in self.listeners:
            await fn()


def _cli() -> None:
    """python -m deckbar_daemon.runs [out.webp] – letzten Run aus der History rendern (ohne zu posten)."""
    import sys
    run = DungeonRuns(Path("/nonexistent")).latest_run()
    if not run:
        sys.exit("keine Dungeon-Runs in der History")
    out = Path(sys.argv[1] if len(sys.argv) > 1 else "run.webp")
    out.write_bytes(render_run(run))
    print(run_message(run), "→", out)


if __name__ == "__main__":
    _cli()
