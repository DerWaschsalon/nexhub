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

TWILIGHT_STRAND = "1_1_1"  # wer hier aufsteigt, ist ein neuer eigener Charakter (Autotrack im Original)
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
        self.zone: ZoneEntered | None = None  # None = Login-Bildschirm oder unbekannt
        self.act = 0  # letzter Kampagnen-Akt: bleibt in Versteck, Labyrinth und Liga-Zonen stehen (wie im Original)
        self.levels: dict[str, LevelUp] = {}  # letzte Stufe je Charakter, auch von Mitspielern
        self.message = ""
        self.guide = Guide()
        self.tracker = Tracker([], self.settings.options())
        self.rebuild()

    @property
    def settings(self) -> LevelingSettings:
        value: LevelingSettings = self.store.value
        return value

    @property
    def character(self) -> str:
        return self.settings.character

    def rebuild(self) -> None:
        """Seiten neu bauen (nach Build-Import, Charakterwechsel, neuem Guide oder geänderten Einstellungen)."""
        self.state.adopt_unnamed(self.character)
        profile = self.state.character(self.character)
        options = self.settings.options()
        custom = self.state.value.custom_guide
        raw = [page for act in custom for page in act] if custom else default_guide()
        self.guide = GuideBuilder(self.data, options, profile.build, profile.gem_sources).build(raw)
        self.tracker = Tracker(self.guide.pages, options, profile.progress)

    # ------------------------------------------------------------ aus Client.txt
    def on_zone(self, zone: ZoneEntered) -> None:
        self.zone = zone
        self.act = self.data.act_of(zone.area_id) or self.act
        if zone.live:
            self.check_zone()

    def on_login(self) -> None:
        self.zone = None

    def check_zone(self) -> bool:
        """Steht man in der Zielzone des Schritts, eine Seite weiter. Das Original prüft das in jeder Runde
        seiner Log-Schleife, nicht nur bei neuen Zeilen: so geht es nach dem Schnellvorlauf und nach der
        Wartezeit beim Blättern von Hand von selbst weiter."""
        if not (self.zone and self.settings.active and self.tracker.entered(self.zone.area_id.lower())):
            return False
        self._moved()
        return True

    def on_level(self, up: LevelUp) -> None:
        """Aufstiege kommen auch für Mitspieler. Eigener Charakter ist der eingestellte; ohne Einstellung der
        erste, der in Twilight Strand aufsteigt. Steigt ein Charakter auf, für den es schon einen Stand gibt,
        spielt man offenbar ihn: dann wird gewechselt."""
        self.levels[up.character] = up
        if up.character == self.character:
            return
        new_here = not self.character and up.live and self.zone and self.zone.area_id == TWILIGHT_STRAND
        if new_here or up.character in self.state.value.characters:
            self.select(up.character)

    def select(self, character: str) -> None:
        self.store.save(self.settings.model_copy(update={"character": character}))
        self.rebuild()

    def level(self) -> LevelUp | None:
        """Stufe des eigenen Charakters; ohne bekannten Charakter keine (lieber keine als die eines Mitspielers)."""
        return self.levels.get(self.character) if self.character else None

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
        if self.tracker.progress != self.state.character(self.character).progress:
            self.state.save_character(self.character, progress=self.tracker.progress)

    def import_code(self, code: str) -> str:
        """PoB-Code oder Guide (JSON im Exile-UI-Format) übernehmen; zurück kommt, was es war."""
        text = code.strip()
        if text.startswith("["):
            return self._import_guide(text)
        build = pob.parse(pob.decode(text), set(self.data.gems))
        self.state.save_character(self.character, build=build)
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
        self.state.save(custom_guide=acts)
        self.state.save_character(self.character, progress=0)
        self.rebuild()
        return "guide"

    def use_default_guide(self) -> None:
        self.state.save(custom_guide=None)
        self.state.save_character(self.character, progress=0)
        self.rebuild()

    def set_gem_sources(self, sources: dict[str, int]) -> None:
        self.state.save_character(self.character,
                                  gem_sources={gem: act for gem, act in sources.items() if 1 <= act <= 10})
        self.rebuild()

    # ------------------------------------------------------------ Anzeige
    def finished(self) -> bool:
        return self.tracker.at_end()

    def _rendered(self) -> Rendered:
        hideout = bool(self.zone and self.zone.area_id.lower().startswith("hideout"))
        renderer = PageRenderer(self.data, self.settings.options(), set(self.layouts))
        return renderer.render(self.tracker.lines, Where(self.act, hideout))

    def _header(self) -> dict[str, Any]:
        up, zone = self.level(), self.zone
        out: dict[str, Any] = {"act": ACT_NAMES.get(self.act, ""), "zone": "", "level": up.level if up else None,
                               "character": self.character, "xp": None}
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
        profile = self.state.character(self.character)
        return {
            **head,
            "xp": {"text": xp.text(), "low": xp.low, "high": xp.high} if xp else None,
            "step": self.tracker.progress + 1, "steps": len(self.guide.pages), "message": self.message,
            "lines": [{"bullet": line.bullet, "segments": [vars(s) for s in line.segments]}
                      for line in rendered.lines],
            "search": gem_search(rendered.buy_gems, self.data) + item_search(rendered.buy_items),
            "build": profile.build.model_dump() if profile.build else None,
            "build_search": gem_search(self._build_gems(), self.data),
            "gems_left": self.guide.gems_left, "gem_sources": profile.gem_sources,
            "custom_guide": self.state.value.custom_guide is not None, "finished": self.finished(),
            # zur Auswahl in der Web-UI: Charaktere mit Stand und die zuletzt im Log aufgestiegenen
            "characters": sorted({*self.state.value.characters, *self.levels} - {""}),
        }

    def _build_gems(self) -> list[str]:
        build = self.state.character(self.character).build
        return sorted(gem for gem in buyable_gems(build) if gem in self.data.gems) if build else []
