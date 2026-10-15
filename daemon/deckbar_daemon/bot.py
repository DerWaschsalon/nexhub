"""Discord-Bot-Anbindung: Kampf- und Run-Ergebnisse an einen Bot schicken, der sie postet.

Gedacht für TheWashBot (Navonex), passt aber zu jedem Bot mit denselben zwei Endpunkten:

Gruppen-DPS (`dps_*`): Endet ein Kampf (dps.py, Kampfende), geht der Endstand der eigenen
Gruppe – nicht aller Spieler in der Nähe – per POST an die Webhook-URL des Bots
(`http://<bot>:8787/dps/<token>`, der Token in der URL wählt Server und Kanal):

    {"target": "Bossname", "duration_s": 83,
     "party": [{"name": "…", "cls": "cleric", "dps": 18432, "dmg": 1529856, "pct": 31.2}]}

Wer zur Gruppe gehört, weiß nur deckbar-capture ab 0.2 (Gruppen-Roster des Spiels, view.rs).
Ohne Gruppe (allein unterwegs) geht nichts raus.

Dungeon-Runs (`runs_*`): Nach jedem beendeten Run (runs.py) zusätzlich zum Bild per Webhook
ein POST mit `Authorization: Bearer <token>` an die Run-API des Bots
(`https://<bot>/api/aion/fight`). Der Bot führt Meldungen mehrerer Spieler vom selben Run zu
einer Rangliste zusammen. Namen sind sprachunabhängig englisch (Dungeon, Bosse), dazu die IDs:

    {"dungeon": "Ferocious Horn Den", "difficulty": "Normal", "dungeon_id": 600123,
     "bosses_total": 3, "bosses_killed": 3, "start_ms": …, "fight_ms": 350000,
     "players": [{"name": "…", "cls": "ranger", "damage": 13290000, "dps": 38000}],
     "bosses": [{"name": "…", "mob": 2400012, "killed": true, "duration_ms": 98000,
                 "players": [{"name": "…", "cls": "ranger", "damage": 4200000, "dps": 41000}]}]}

Beides schickt Charakternamen von Mitspielern an einen fremden Server. Deshalb ist alles
standardmäßig aus und wird nur mit eingetragener Adresse aktiv.
"""
from __future__ import annotations

import logging
import re
import time
from datetime import datetime
from pathlib import Path
from typing import Awaitable, Callable

import aiohttp
import yaml
from pydantic import Field, ValidationError, field_validator

from .config import _atomic_write, _Strict
from .runs import Run, boss_name_en, dungeon_parts_en

log = logging.getLogger(__name__)

URL_RE = re.compile(r"^https?://[^\s/?#]+(?::\d+)?(?:/[^\s]*)?$")
TIMEOUT_S = 20
# so viel % HP darf am Boss übrig sein und er gilt trotzdem als besiegt (Rundung im Meter)
KILL_HP = 0.5
MASK = "•" * 8


def _url(v: str) -> str:
    v = v.strip()
    if v and not URL_RE.match(v):
        raise ValueError("keine http(s)-Adresse")
    return v


class BotSettings(_Strict):
    # ---- Gruppen-DPS nach jedem Kampf
    dps_enabled: bool = False
    dps_url: str = Field("", max_length=300)
    # nur Bosse, nur besiegte, erst ab so vielen Sekunden, erst ab so vielen Gruppenmitgliedern
    dps_boss_only: bool = True
    dps_kills_only: bool = True
    dps_min_seconds: int = Field(20, ge=0, le=3600)
    dps_min_party: int = Field(2, ge=1, le=8)
    # ---- Dungeon-Runs
    runs_enabled: bool = False
    runs_url: str = Field("", max_length=300)
    runs_token: str = Field("", max_length=200)

    @field_validator("dps_url", "runs_url")
    @classmethod
    def _urls(cls, v: str) -> str:
        return _url(v)

    @field_validator("runs_token")
    @classmethod
    def _token(cls, v: str) -> str:
        v = v.strip()
        if any(c.isspace() for c in v):
            raise ValueError("Token ohne Leerzeichen")
        return v


# ---------------------------------------------------------------- Inhalte
def group_payload(fight: dict, s: BotSettings) -> tuple[dict | None, str]:
    """Endstand eines Kampfs (dps.fight_view) → Payload, oder None und der Grund, warum nicht."""
    rows = fight.get("rows") or []
    if not rows:
        return None, "keine Zeilen"
    if any(r.get("party") is None for r in rows):
        return None, "Quelle kennt die Gruppe nicht (deckbar-capture ab 0.2 nötig)"
    party = [r for r in rows if r["party"]]
    you = next((r for r in rows if r.get("you")), None)
    if party and you and you not in party:
        party.append(you)  # das Roster nennt einen selbst nicht immer
    if len(party) < s.dps_min_party:
        return None, f"Gruppe zu klein ({len(party)})"
    if s.dps_boss_only and not fight.get("boss"):
        return None, "kein Boss"
    hp = fight.get("hp")
    if s.dps_kills_only and not (hp is not None and hp <= KILL_HP):
        return None, "nicht besiegt"
    secs = int(fight.get("time") or 0)
    if secs < s.dps_min_seconds:
        return None, f"zu kurz ({secs} s)"
    total = sum(r["dmg"] for r in party) or 1
    party = sorted(party, key=lambda r: -r["dps"])
    return {
        "target": fight.get("target") or "Kampf",
        "duration_s": secs,
        "party": [{"name": r["name"], "cls": r["cls"], "dps": r["dps"], "dmg": r["dmg"],
                   "pct": round(100 * r["dmg"] / total, 1)} for r in party],
    }, ""


def _players(players: dict, ms: int) -> list[dict]:
    secs = max(1.0, ms / 1000)
    out = [{"name": p.name, "cls": p.cls, "damage": p.dmg, "dps": round(p.dmg / secs)}
           for p in players.values() if p.dmg > 0]
    return sorted(out, key=lambda p: -p["damage"])


def run_payload(run: Run) -> dict:
    """Beendeter Run (Namen schon per rename aufgelöst) → Payload der Run-API."""
    bosses = run.bosses()
    fight_ms = sum(b.duration_ms for b in bosses)
    name, diff = dungeon_parts_en(run.dungeon)
    return {
        "dungeon": name,
        "difficulty": diff,
        "dungeon_id": run.dungeon,
        "bosses_total": len(bosses),
        "bosses_killed": run.kills,
        "complete": run.complete,
        "start_ms": run.start_ms,
        "end_ms": run.end_ms,
        "fight_ms": fight_ms,
        "players": _players(run.total().players, fight_ms),
        "bosses": [{"name": boss_name_en(b.mob, b.name), "mob": b.mob, "killed": b.killed,
                    "duration_ms": b.duration_ms, "players": _players(b.players, b.duration_ms)}
                   for b in bosses if b.total > 0],
    }


async def post_json(session: aiohttp.ClientSession, url: str, payload: dict, token: str = "") -> None:
    headers = {"User-Agent": "DeckBar"}
    if token:
        headers["Authorization"] = f"Bearer {token}"
    async with session.post(url, json=payload, headers=headers) as resp:
        if resp.status >= 300:
            body = (await resp.text())[:200]
            raise RuntimeError(f"Bot antwortet {resp.status}: {body}")


# ---------------------------------------------------------------- Dienst
class DiscordBot:
    def __init__(self, config_dir: Path) -> None:
        self.path = config_dir / "bot.yaml"
        self.settings = self._load()
        self.enabled = False  # Modul an (ModuleManager); Einstellungen gelten nur dann
        self.last_fight: dict | None = None  # letzter Kampfende-Stand (Test-Knopf)
        self.last_run: Run | None = None
        self.result: dict[str, dict] = {"dps": {}, "runs": {}}  # letzter Versand je Weg
        self.listeners: list[Callable[[], Awaitable[None]]] = []
        self._session: aiohttp.ClientSession | None = None
        self._sent: tuple | None = None  # (Ziel-ID, Ziel, Dauer) des zuletzt geschickten Kampfs

    def _load(self) -> BotSettings:
        try:
            return BotSettings.model_validate(yaml.safe_load(self.path.read_text()) or {})
        except FileNotFoundError:
            return BotSettings()
        except (yaml.YAMLError, ValidationError) as e:
            log.error("%s ungültig, nutze Standardwerte: %s", self.path, e)
            return BotSettings()

    def save(self, settings: BotSettings) -> None:
        header = "# Discord-Bot-Anbindung – wird von der Web-UI überschrieben. Enthält Geheimnisse.\n"
        text = yaml.safe_dump(settings.model_dump(), sort_keys=False, allow_unicode=True)
        _atomic_write(self.path, header + text, 0o600)
        self.settings = settings

    def update(self, data: dict) -> BotSettings:
        """Teil-Update aus der Web-UI; Platzhalter (•••) lassen Geheimnisse unverändert."""
        merged = self.settings.model_dump()
        for k, v in data.items():
            if k in ("dps_url", "runs_url", "runs_token") and isinstance(v, str) and v and set(v) == {"•"}:
                continue
            merged[k] = v
        settings = BotSettings.model_validate(merged)
        self.save(settings)
        return settings

    def info(self) -> dict:
        s = self.settings.model_dump()
        for k in ("dps_url", "runs_url", "runs_token"):
            if s[k]:
                s[k] = MASK
        # Adresse ohne Token zeigen, damit man sieht, wohin es geht
        host = lambda u: re.sub(r"^(https?://[^/]+).*$", r"\1/…", u) if u else ""  # noqa: E731
        return {
            "settings": s,
            "targets": {"dps": host(self.settings.dps_url), "runs": host(self.settings.runs_url)},
            "result": self.result,
            "last_fight": self._fight_summary(self.last_fight),
            "last_run": {"name": self.last_run.name, "end": self.last_run.end_ms} if self.last_run else None,
        }

    @staticmethod
    def _fight_summary(f: dict | None) -> dict | None:
        if not f:
            return None
        return {"target": f.get("target"), "time": f.get("time"), "boss": f.get("boss"), "hp": f.get("hp"),
                "party": sum(1 for r in f.get("rows") or [] if r.get("party"))}

    async def _changed(self) -> None:
        for fn in self.listeners:
            await fn()

    def _note(self, kind: str, ok: bool, text: str) -> None:
        self.result[kind] = {"ok": ok, "text": text, "at": int(time.time())}
        (log.info if ok else log.warning)("Discord-Bot (%s): %s", kind, text)

    def session(self) -> aiohttp.ClientSession:
        if self._session is None or self._session.closed:
            self._session = aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=TIMEOUT_S))
        return self._session

    async def close(self) -> None:
        if self._session and not self._session.closed:
            await self._session.close()

    # ------------------------------------------------------------ Gruppen-DPS
    async def on_fight(self, fight: dict) -> None:
        """Kampfende (DpsFeed.fight_listeners)."""
        self.last_fight = fight
        s = self.settings
        if not (self.enabled and s.dps_enabled and s.dps_url):
            await self._changed()
            return
        key = (fight.get("target_id"), fight.get("target"), fight.get("time"))
        if key == self._sent:
            return
        payload, why = group_payload(fight, s)
        if payload is None:
            log.debug("Gruppen-DPS nicht gesendet: %s", why)
            await self._changed()
            return
        if await self.send_fight(payload):
            self._sent = key

    async def send_fight(self, payload: dict) -> bool:
        try:
            await post_json(self.session(), self.settings.dps_url, payload)
        except (aiohttp.ClientError, TimeoutError, RuntimeError, OSError) as e:
            self._note("dps", False, f"{payload['target']}: {e or type(e).__name__}")
            await self._changed()
            return False
        self._note("dps", True, f"{payload['target']} ({len(payload['party'])} Spieler, {datetime.now():%H:%M})")
        await self._changed()
        return True

    async def test_fight(self) -> tuple[bool, str]:
        """Knopf in der Web-UI: letzten Kampf schicken, ohne die Filter (Boss, Sieg, Dauer)."""
        if not self.settings.dps_url:
            return False, "keine Webhook-URL eingetragen"
        if not self.last_fight:
            return False, "seit dem Start noch kein Kampf beendet"
        relaxed = self.settings.model_copy(update={"dps_boss_only": False, "dps_kills_only": False,
                                                   "dps_min_seconds": 0, "dps_min_party": 1})
        payload, why = group_payload(self.last_fight, relaxed)
        if payload is None:
            return False, why
        ok = await self.send_fight(payload)
        return ok, self.result["dps"].get("text", "")

    # ------------------------------------------------------------ Runs
    async def on_run(self, run: Run) -> None:
        """Beendeter Run (DungeonRuns.run_listeners)."""
        self.last_run = run
        s = self.settings
        if self.enabled and s.runs_enabled and s.runs_url and s.runs_token:
            await self.send_run(run)
        else:
            await self._changed()

    async def send_run(self, run: Run) -> bool:
        try:
            await post_json(self.session(), self.settings.runs_url, run_payload(run), self.settings.runs_token)
        except (aiohttp.ClientError, TimeoutError, RuntimeError, OSError) as e:
            self._note("runs", False, f"{run.name}: {e or type(e).__name__}")
            await self._changed()
            return False
        self._note("runs", True, f"{run.name}, {datetime.fromtimestamp(run.end_ms / 1000):%d.%m. %H:%M}")
        await self._changed()
        return True

    async def test_run(self, run: Run | None) -> tuple[bool, str]:
        if not (self.settings.runs_url and self.settings.runs_token):
            return False, "Adresse oder Token der Run-API fehlt"
        if run is None:
            return False, "noch kein Dungeon-Run in der History"
        ok = await self.send_run(run)
        return ok, self.result["runs"].get("text", "")

