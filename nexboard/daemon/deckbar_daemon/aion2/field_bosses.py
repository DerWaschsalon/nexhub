"""Feldbosse: Respawn-Timer aus der Liste, die das Spiel bei offener Karte schickt, ihre Namen, die Tabelle
der Seite „Termine“ und die Ansagen (auch für den Riss).

Ein Platz ist ein dict mit karte, lebt, pos, zeit (lebt: seit wann, tot: Respawn) und npc. So liegt er auch
in feldbosse.json, damit die Timer einen Neustart überleben.
"""
from __future__ import annotations

import math
import time
from collections.abc import Callable

from nexproto.termine import EVENT_BY_KEY, next_start

from ..core.packets import PacketSource
from ..core.packets.messages import FieldBossList, NpcSeen
from .gamedata import BOSSES, field_boss_npcs, load_state, npc_name, save_state
from .rules import language, tr
from .settings import Settings
from .world import World

STATE_FILE = "feldbosse.json"
MAP_OPEN_S = 2.5  # so lange nach der letzten Liste gilt die Karte im Spiel als offen
NEAR_CM = 5000  # ein Boss, der höchstens 50 m neben einem Platz erscheint, ist dieser Feldboss
PROBABLY_UP_S = 2 * 3600  # so lange nach dem Respawn gilt ein Feldboss als „vermutlich da“
OK, WARN, QUIET = "ok", "warn", "leise"  # Farbklassen der NexBoard-Seite
ANNOUNCE_AT = ((300, " in 5 Minuten"), (0, None))  # (Sekunden vorher, Satz; None = der Satz „ist da/offen“)
LATE_S = 30  # nicht nachträglich ansagen, z. B. nach dem Einloggen
NEVER = 1e9


class FieldBossTracker:
    def __init__(self, world: World, persist: bool = False) -> None:
        self.world = world
        self.persist = persist  # nicht beim Abspielen alter Mitschnitte
        self.slots: dict[str, dict] = load_state(STATE_FILE) if persist else {}
        self.list_seen = 0.0

    def attach(self, source: PacketSource) -> None:
        source.on(FieldBossList, self._on_list)
        source.on(NpcSeen, self._on_npc)

    @property
    def map_open(self) -> bool:
        return time.time() - self.list_seen < MAP_OPEN_S

    def alive_here(self) -> list[dict]:
        return [b for b in self.slots.values() if b["lebt"] and b["pos"] and b["karte"] == self.world.zone]

    def _on_list(self, m: FieldBossList) -> None:
        self.list_seen = time.time()
        if m.slots is None:
            return
        fresh = {}
        for slot in m.slots:
            old = self.slots.get(str(slot.slot), {})
            fresh[str(slot.slot)] = {"karte": m.map_id, "lebt": slot.alive, "pos": slot.position or old.get("pos"),
                                     "zeit": slot.time, "npc": old.get("npc")}
        if any(self.slots.get(k) != v for k, v in fresh.items()):
            self.slots.update(fresh)
            self._save()

    def _on_npc(self, m: NpcSeen) -> None:
        if m.npc in BOSSES or m.npc not in field_boss_npcs() or not m.position:
            return
        for slot in self.slots.values():
            if slot["pos"] and slot["npc"] != m.npc and math.dist(slot["pos"], m.position) < NEAR_CM:
                slot["npc"] = m.npc
                self._save()

    def _save(self) -> None:
        if self.persist:
            save_state(STATE_FILE, self.slots)


def rift(now: float) -> tuple[float, bool]:
    return next_start(now, EVENT_BY_KEY["rift"])


def slot_name(slot_id: str, slot: dict) -> str:
    return npc_name(slot["npc"], language()) if slot.get("npc") else f"{tr('Feldboss')} {int(slot_id) % 100}"


def slot_status(slot: dict, now: float) -> tuple[str, str, float]:
    """(Anzeige, Farbe, Sekunden bis Respawn) für einen Feldboss-Platz."""
    rest = slot["zeit"] - now
    if slot["lebt"]:
        return tr("lebt"), OK, 0
    if rest > 0:
        return f"{tr('in')} {int(rest // 3600)}:{int(rest % 3600 // 60):02}:{int(rest % 60):02}", WARN, rest
    if slot["zeit"] and -rest < PROBABLY_UP_S:
        return tr("vermutlich da"), OK, 0
    return tr("unbekannt"), QUIET, NEVER


def overview(slots: dict[str, dict], zone: int | None) -> list[dict]:
    """Alle bekannten Plätze für die Seite „Termine“: die der aktuellen Karte zuerst, dann nach Respawn."""
    now, rows = time.time(), []
    for slot_id, slot in slots.items():
        text, color, rest = slot_status(slot, now)
        here = slot["karte"] == zone
        rows.append((not here, rest, {"name": slot_name(slot_id, slot), "karte": slot["karte"], "status": text,
                                      "farbe": color, "hier": here}))
    return [row for *_, row in sorted(rows, key=lambda row: row[:2])]


class FieldBossCalls:
    """Ansage 5 Minuten vor dem Respawn und beim Respawn, nur für die aktuelle Karte; dazu der Riss."""

    def __init__(self, tracker: FieldBossTracker, say: Callable[[str], None], settings: Settings) -> None:
        self.tracker = tracker
        self.settings = settings
        self.say = say
        self.announced: set[tuple] = set()

    def tick(self) -> None:
        if not self.settings.field_bosses.announce:
            return
        now = time.time()
        opens, _ = rift(now)
        self._announce("riss", opens, opens - now, tr("Riss"), " ist offen")
        for slot_id, slot in list(self.tracker.slots.items()):
            rest = slot["zeit"] - now
            if slot["karte"] == self.tracker.world.zone and not slot["lebt"] and rest >= -10:
                self._announce(slot_id, slot["zeit"], rest, slot_name(slot_id, slot), " ist da")

    def _announce(self, what: str, at: float, rest: float, name: str, arrived: str) -> None:
        for limit, sentence in ANNOUNCE_AT:
            key = (what, at, limit)
            if rest <= limit and key not in self.announced:
                self.announced.add(key)
                if rest > limit - LATE_S:
                    self.say(name + tr(sentence or arrived))
