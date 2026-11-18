"""Der Leveling-Guide als Ganzes: Seiten bauen, Stand führen, auf Zonen und Aufstiege reagieren, anzeigen.

Weiß nichts von Bus, Web oder Leiste; das Modul (modules/poe_leveling.py) reicht Ereignisse herein und
holt view() für Web-UI und device() für die Kachel ab.
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from nexcore.settings import SettingsStore

from ..client_log import LevelUp, ZoneEntered
from . import pob
from .data import DATA_DIR, default_guide, load
from .device_view import device_lines
from .experience import experience
from .guide import GuideBuilder, buyable_gems
from .markup import PageRenderer, Rendered, Where
from .search import gem_search, item_search
from .settings import LevelingSettings, StateFile
from .terms import ACT_NAMES, AREA, BANDITS, Guide
from .tracker import Tracker

MESSAGES = {
    "end": "Ende des Guides",
    "start": "Schon am Anfang",
    "not_ahead": "Diese Zone kommt im Guide nicht mehr vor",
    "no_zone": "Zone unbekannt – erst eine Zone betreten",
}
LAYOUT_DIR = DATA_DIR / "hints"


def layout_names() -> dict[str, Path]:
    """Layout-Bilder unter ihrem Namen im Guide („opposite corners1“)."""
    return {file.stem.replace("_", " "): file for file in sorted(LAYOUT_DIR.glob("*.jpg"))}


def is_town(area_id: str) -> bool:
    return "_town" in area_id or area_id.lower().startswith("hideout")


class Leveling:
    def __init__(self, store: SettingsStore[LevelingSettings], state_file: Path) -> None:
        self.store = store
        self.state = StateFile(state_file)
        self.data = load()
        self.layouts = layout_names()
        self.zone: ZoneEntered | None = None
        self.levels: dict[str, LevelUp] = {}
        self.last_up: LevelUp | None = None  # wer zuletzt aufgestiegen ist
        self.message = ""
        self.guide = Guide()
        self.tracker = Tracker([], self.settings.options())
        self.rebuild()

    @property
    def settings(self) -> LevelingSettings:
        value: LevelingSettings = self.store.value
        return value

    def rebuild(self) -> None:
        """Seiten neu bauen (nach Build-Import, neuem Guide oder geänderten Einstellungen)."""
        state = self.state.value
        options = self.settings.options()
        raw = [page for act in state.custom_guide for page in act] if state.custom_guide else default_guide()
        self.guide = GuideBuilder(self.data, options, state.build, state.gem_sources).build(raw)
        self.tracker = Tracker(self.guide.pages, options, state.progress)

    # ------------------------------------------------------------ aus Client.txt
    def on_zone(self, zone: ZoneEntered) -> None:
        self.zone = zone
        if zone.live:
            self.check_zone()

    def check_zone(self) -> bool:
        """Steht man in der Zielzone des Schritts, eine Seite weiter. Das Original prüft das in jeder Runde
        seiner Log-Schleife, nicht nur bei neuen Zeilen: so geht es nach dem Schnellvorlauf und nach der
        Wartezeit beim Blättern von Hand von selbst weiter."""
        if not (self.zone and self.settings.active and self.tracker.entered(self.zone.area_id.lower())):
            return False
        self._moved()
        return True

    def on_level(self, up: LevelUp) -> None:
        self.levels[up.character] = up
        self.last_up = up

    def level(self) -> LevelUp | None:
        name = self.settings.character
        return self.levels.get(name) if name else self.last_up

    # ------------------------------------------------------------ Bedienung
    def command(self, name: str) -> None:
        """next, back, skip (Schnellvorlauf zur aktuellen Zone) oder reset (von vorn)."""
        actions = {"next": self._next, "back": self._back, "skip": self._skip, "reset": self.tracker.reset}
        if name not in actions:
            raise ValueError(f"unbekannter Befehl {name}")
        self.message = ""
        actions[name]()
        self._moved()

    def _next(self) -> None:
        if not self.tracker.next():
            self.message = MESSAGES["end"]

    def _back(self) -> None:
        if not self.tracker.back():
            self.message = MESSAGES["start"]

    def _skip(self) -> None:
        if not self.zone:
            self.message = MESSAGES["no_zone"]
        elif not self.tracker.skip_to(self.zone.area_id.lower()):
            self.message = MESSAGES["not_ahead"]

    def _moved(self) -> None:
        if self.tracker.progress != self.state.value.progress:
            self.state.save(progress=self.tracker.progress)

    def import_code(self, code: str) -> str:
        """PoB-Code oder Guide (JSON im Exile-UI-Format) übernehmen; zurück kommt, was es war."""
        text = code.strip()
        if text.startswith("["):
            return self._import_guide(text)
        build = pob.parse(pob.decode(text), set(self.data.gems))
        self.state.save(build=build)
        bandit = build.bandit if build.bandit in BANDITS else "none"
        self.store.save(self.settings.model_copy(update={"bandit": bandit}))
        self.rebuild()
        return "build"

    def _import_guide(self, text: str) -> str:
        try:
            acts = json.loads(text)
        except json.JSONDecodeError as e:
            raise pob.PobError("Guide ist kein gültiges JSON") from e
        if not isinstance(acts, list) or not any(AREA in json.dumps(act) for act in acts):
            raise pob.PobError("Das sieht nicht nach einem Exile-UI-Guide aus")
        self.state.save(custom_guide=acts, progress=0)
        self.rebuild()
        return "guide"

    def use_default_guide(self) -> None:
        self.state.save(custom_guide=None, progress=0)
        self.rebuild()

    def set_gem_sources(self, sources: dict[str, int]) -> None:
        self.state.save(gem_sources={gem: act for gem, act in sources.items() if 1 <= act <= 10})
        self.rebuild()

    # ------------------------------------------------------------ Anzeige
    def finished(self) -> bool:
        return self.tracker.at_end()

    def _rendered(self) -> Rendered:
        area = self.zone.area_id if self.zone else ""
        where = Where(self.data.act_of(area), area.lower().startswith("hideout"))
        renderer = PageRenderer(self.data, self.settings.options(), set(self.layouts))
        return renderer.render(self.tracker.lines, where)

    def _header(self) -> dict[str, Any]:
        up, zone = self.level(), self.zone
        act = self.data.act_of(zone.area_id) if zone else 0
        out: dict[str, Any] = {"act": ACT_NAMES.get(act, ""), "zone": "", "level": up.level if up else None,
                               "character": up.character if up else "", "xp": None}
        if zone:
            area = self.data.areas.get(zone.area_id.lower())
            out["zone"] = area.name if area else zone.area_id
        if up and zone:
            out["xp"] = experience(up.level, zone.area_level, is_town(zone.area_id))
        return out

    def device(self) -> dict[str, Any]:
        """Inhalt der Guide-Kachel (state.guide)."""
        head = self._header()
        parts = [head["act"], f"Lv {head['level']}" if head["level"] else "",
                 f"XP {head['xp'].text()}" if head["xp"] else ""]
        return {"head": " · ".join(p for p in parts if p),
                "step": f"{self.tracker.progress + 1}/{len(self.guide.pages)}",
                "lines": device_lines(self._rendered()), "msg": self.message}

    def view(self) -> dict[str, Any]:
        """Alles für die Seite in der Web-UI."""
        rendered = self._rendered()
        head = self._header()
        xp = head.pop("xp")
        state = self.state.value
        return {
            **head,
            "xp": {"text": xp.text(), "low": xp.low, "high": xp.high} if xp else None,
            "step": self.tracker.progress + 1, "steps": len(self.guide.pages), "message": self.message,
            "lines": [{"bullet": line.bullet, "segments": [vars(s) for s in line.segments]}
                      for line in rendered.lines],
            "search": gem_search(rendered.buy_gems, self.data) + item_search(rendered.buy_items),
            "build": state.build.model_dump() if state.build else None,
            "build_search": gem_search(self._build_gems(), self.data),
            "gems_left": self.guide.gems_left, "gem_sources": state.gem_sources,
            "custom_guide": state.custom_guide is not None, "finished": self.finished(),
        }

    def _build_gems(self) -> list[str]:
        build = self.state.value.build
        return sorted(gem for gem in buyable_gems(build) if gem in self.data.gems) if build else []
