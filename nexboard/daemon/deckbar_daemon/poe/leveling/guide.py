"""Seiten des Guides für einen Build bauen (Leveltracker_Load im Original).

Aus den Gems des PoB-Builds wird je Quest-Zeile eine Belohnung („take: X“) bzw. ein Kauf („buy gem: X“),
Quests ohne Nutzen werden gestrichen oder als übersprungen markiert, „quest-check“-Seiten ohne Nutzen
fallen weg. Die Reihenfolgen (alphabetisch) und Sonderfälle (Lilly, Quicksilver) sind die des Originals,
damit dieselbe Gem-Liste dieselben Seiten ergibt.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field

from .data import LevelingData
from .pob import PobBuild
from .terms import BUY_GEM, GEM_REWARD, QUEST, QUEST_CHECK, STAT_COLORS, Guide, Options, Page

STARTER_GEMS = {  # hat die Klasse von Anfang an, also nie als Belohnung
    "witch": ("fireball", "arcane surge"),
    "shadow": ("viper strike", "chance to poison"),
    "ranger": ("burning arrow", "momentum"),
    "duelist": ("double strike", "chance to bleed"),
    "marauder": ("heavy strike", "ruthless"),
    "templar": ("holy strike", "hallow"),
    "scion": ("spectral throw", "prismatic burst"),
}
NOT_BOUGHT = ("empower", "enhance", "enlighten")  # gibt es nicht bei Händlern
QUICKSILVER = "quicksilver flask"  # beim Ligastart die erste Belohnung; daneben darf es noch ein Gem geben
LILLY = "lilly"
LILLY_LINE = "lilly:"
LILLY_QUESTS = re.compile(r"mercy.mission|a.fixture.of.fate|fallen.from.grace", re.IGNORECASE)
LILLY_SHOP = re.compile(r"lilly.*(mercy.mission|a.fixture.of.fate|fallen.from.grace)", re.IGNORECASE)
LILLY_TAIL = " || lilly:"
BREAKING_EGGS = "breaking_some_eggs"
NPC = re.compile(r":.?<")  # „tarkleigh: <quest>“
SKIP_IMAGE = "(img:skip)"
FOLLOW_UPS = re.compile(r"\(hint\)|\(img:quest\)", re.IGNORECASE)  # gehören zur Quest-Zeile darüber


@dataclass
class PageWork:
    """Was beim Bau einer Seite anfällt."""
    lines: list[str] = field(default_factory=list)
    quests: set[str] = field(default_factory=set)
    rewards: set[str] = field(default_factory=set)  # Quests mit Belohnung für den Build
    vendors: set[str] = field(default_factory=set)  # Quests, nach denen ein Gem gekauft wird
    quest_check: bool = False


class GuideBuilder:
    def __init__(self, data: LevelingData, options: Options, build: PobBuild | None,
                 gem_sources: dict[str, int]) -> None:
        self.data = data
        self.options = options
        self.char_class = build.char_class if build else ""
        self.gem_sources = gem_sources  # Gem → Akt, in dem es gekauft wird (fehlt: wo es zuerst geht)
        self.gems = self._wanted_gems(build)
        # bleiben wie im Original über Seiten hinweg bestehen
        self._skipped: dict[int, dict[str, list[str]]] = {}
        self._act = 0

    def build(self, raw_pages: list[object]) -> Guide:
        pages = [Page.from_raw(raw) for raw in raw_pages]
        kept = []
        for index, page in enumerate(pages):
            if page.applies(self.options) and page.contains(": <"):
                following = pages[index + 1] if index + 1 < len(pages) else None
                if not self._rebuild(page, following):
                    continue
            kept.append(page)
        return Guide(kept, [g for g in self.gems if g])

    # ------------------------------------------------------------ welche Gems
    def _wanted_gems(self, build: PobBuild | None) -> list[str]:
        gems = [QUICKSILVER] if self.options.league_start else []
        if not build:
            return gems
        wanted = buyable_gems(build)
        rewards = sorted(key for key in wanted if self._reward_only(key))
        vendors = sorted(key for key in wanted if not self._reward_only(key))
        return gems + rewards + vendors

    def _reward_only(self, gem: str) -> bool:
        """Gibt es das Gem für die Klasse als Belohnung, aber bei dem Händler danach nicht zu kaufen?"""
        for quest, info in self.data.gem(gem).get("quests", {}).items():
            if (self.data.quests.get(quest, {}).get("npc") and self._for_class(info.get("quest"))
                    and info.get("vendor") and not self._for_class(info["vendor"])):
                return True
        return False

    def _for_class(self, classes: list[str] | None) -> bool:
        return self.char_class in [c.lower() for c in classes or []]

    def _bought_here(self, gem: str, quest: str) -> bool:
        """Passt die Quelle, die der Nutzer für das Gem gewählt hat (Akt), zu dieser Quest?"""
        act = self.gem_sources.get(gem)
        return not act or act == self.data.quests.get(quest, {}).get("act")

    # ------------------------------------------------------------ eine Seite
    def _rebuild(self, page: Page, following: Page | None) -> bool:
        """Zeilen der Seite neu setzen; False = Seite fällt weg (quest-check ohne Nutzen)."""
        work = PageWork()
        for line in page.lines:
            self._take_line(line, work)
        if work.quests and self.options.gem_hints:
            self._insert_purchases(work, page, following)
        self.gems = [g for g in self.gems if g]
        self._mark_skipped(work)
        page.lines = work.lines
        return not (work.quest_check and not (work.rewards or work.vendors))

    def _take_line(self, line: str, work: PageWork) -> None:
        if "<" not in line:
            work.lines.append(line)
            return
        if self.options.skips(line):
            return
        quests = [q.replace("_", " ") for q in QUEST.findall(line)]
        work.quests.update(quests)
        if QUEST_CHECK in line:
            work.quest_check = True
            return
        work.lines.append(line)
        if self.options.gem_hints and not LILLY_SHOP.search(line):
            for quest in quests:
                self._add_rewards(quest, work)

    def _add_rewards(self, quest: str, work: PageWork) -> None:
        """Belohnung für die Quest: das erste passende Gem (Quicksilver darf ein zweites mitbringen)."""
        for index, gem in enumerate(self.gems):
            if not gem:
                continue
            info = self.data.gem(gem).get("quests", {}).get(quest)
            if not info or "quest" not in info:
                continue
            if info["quest"] and not self._for_class(info["quest"]):
                continue
            if not self._bought_here(gem, quest):
                continue
            work.lines.append(self._reward_line(gem))
            self.gems[index] = ""
            work.rewards.add(quest)
            if gem != QUICKSILVER:
                return

    def _reward_line(self, gem: str) -> str:
        info = self.data.gem(gem)
        attribute = info.get("attribute")
        color = f"(color:{STAT_COLORS[attribute - 1]})" if attribute else ""
        name = (info.get("name") or gem).replace(" support", "").replace(" ", "_")
        return f"(hint)__ {GEM_REWARD} {color}{name}"

    def _insert_purchases(self, work: PageWork, page: Page, following: Page | None) -> None:
        """Gems, die nach den Quests der Seite beim Händler zu haben sind, als „buy gem“-Zeile."""
        for index, gem in enumerate(self.gems):
            if not gem:
                continue
            quest = self._vendor_quest(gem, work)
            if not quest:
                continue
            work.vendors.add(quest)
            # Folgt eine gleichwertige quest-check-Seite, kauft man erst dort (wie im Original)
            if (work.quest_check and following is not None and following.condition == page.condition
                    and following.contains(QUEST_CHECK)):
                return
            self.gems[index] = ""
            work.lines.insert(_after_last_quest(work.lines), f"{BUY_GEM} {gem}")

    def _vendor_quest(self, gem: str, work: PageWork) -> str | None:
        for quest, info in sorted(self.data.gem(gem).get("quests", {}).items()):
            vendor = info.get("vendor")
            if quest not in work.quests or not isinstance(vendor, list):
                continue
            if vendor and not self._for_class(vendor):
                continue
            if self._bought_here(gem, quest):
                return str(quest)
        return None

    # ------------------------------------------------------------ Quests ohne Nutzen
    def _mark_skipped(self, work: PageWork) -> None:
        """Von unten nach oben: Quest-Zeilen ohne Nutzen streichen oder die Quest als übersprungen zeigen."""
        for index in range(len(work.lines) - 1, -1, -1):
            self._mark_line(index, work)

    def _mark_line(self, index: int, work: PageWork) -> None:
        line = work.lines[index]
        quest_count = line.count("<")  # vor dem Abschneiden des Lilly-Teils, wie im Original
        npc = self._npc(line)
        useless = self._collect_skipped(line, npc, work)
        lilly_at = line.find(LILLY_TAIL)
        if lilly_at >= 0:
            line = work.lines[index] = line[:lilly_at]
        if quest_count and useless == quest_count:
            if not self.options.gems_all or lilly_at >= 0:
                work.lines.pop(index)
            return
        skipped = self._skipped.get(self._act, {}).get(npc)
        if f"{LILLY_LINE} <" not in line and npc and skipped:
            work.lines[index] = _with_skip_marks(line, skipped)
            self._skipped[self._act].pop(npc)

    def _npc(self, line: str) -> str:
        match = NPC.search(line)
        if not match:
            return ""
        npc = line[:match.start()]
        # Die Belohnung für „Breaking some Eggs“ holt man bei Tarkleigh, auch wenn Lilly in der Zeile steht
        return "tarkleigh" if LILLY in npc and BREAKING_EGGS in line else npc

    def _collect_skipped(self, line: str, npc: str, work: PageWork) -> int:
        """Quests der Zeile ohne Belohnung merken; zurück kommt, wie viele davon nichts bringen."""
        useless = 0
        lilly_line = f"{LILLY_LINE}" in line
        for quest, info in sorted(self.data.quests.items()):
            if quest.replace(" ", "_") not in line:
                continue
            self._act = info.get("act", 0)
            if quest in work.rewards:
                continue
            lilly_sells = self.options.league_start and "fallen_from_grace" in line or bool(work.vendors)
            if not (lilly_line and lilly_sells):
                useless += 1
            if not (lilly_line and LILLY_QUESTS.search(quest)):
                self._skipped.setdefault(self._act, {}).setdefault(npc, []).append(quest.replace(" ", "_"))
        return useless


def buyable_gems(build: PobBuild) -> set[str]:
    """Gems des Builds, die man unterwegs bekommt oder kauft (ohne Startgems der Klasse und ohne Empower & Co.)."""
    starter = STARTER_GEMS.get(build.char_class, ())
    return {gem.key for skill_set in build.skill_sets for group in skill_set.groups for gem in group.gems
            if not any(word in gem.name for word in NOT_BOUGHT) and gem.name not in starter}


def _after_last_quest(lines: list[str]) -> int:
    """Einfügestelle hinter der letzten Quest-Zeile samt ihren Unterpunkten."""
    quest_lines = [i for i, line in enumerate(lines) if ": <" in line.lower()]
    position = quest_lines[-1] + 1 if quest_lines else 0
    while position < len(lines) and FOLLOW_UPS.search(lines[position]):
        position += 1
    return position


def _with_skip_marks(line: str, skipped: list[str]) -> str:
    """Übersprungene Quests in der Zeile durch das Überspringen-Bild ersetzen, fehlende vorn ergänzen."""
    extra = []
    for quest in skipped:
        if quest in line:
            line = line.replace(f"<{quest}>", SKIP_IMAGE)
        else:
            extra.append(SKIP_IMAGE)
    return line.replace(": ", ": " + ", ".join(extra) + ", ") if extra else line
