"""Zeilen einer Guide-Seite in farbige Stücke zerlegen (Leveltracker_PageDraw im Original).

Ergebnis ist neutral (Text, Farbe, Bild); wie es aussieht, entscheiden Leiste und Web-UI. Die Farben
sind die von Exile-UI, damit der Guide vertraut aussieht: Zonen hellorange, Gegner orange, Quests gelb.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field

from .data import LevelingData
from .terms import (
    ACT_NAMES,
    AREA,
    BUY_GEM,
    BUY_ITEM,
    HINT,
    KILL,
    LEAGUE_START,
    LEVEL_HINTS,
    OPTIONAL,
    QUEST_CHECK,
    TWINK,
    Options,
)
from .tracker import strip_comment

WHITE = "FFFFFF"
AREA_COLOR = "FEC076"
KILL_COLOR = "FF8111"
QUEST_COLOR = "FFDB1F"
QUEST_ITEM_COLOR = "00FF00"
LAB_COLOR = "569777"
ARENA_COLOR = "CC99FF"  # was hinter (img:arena) bzw. (img:in-out2) steht
LAYOUT_COLOR = "00FFFF"  # Begriff mit Layout-Bild
BUY_COLOR = "FF00FF"
TAGS = (OPTIONAL, LEAGUE_START, TWINK)
NO_SPACE_BEFORE = ",.:)"
NOT_KILLED = ("everything,", "it")  # „kill everything“ / „kill it“: das Wort danach ist kein Gegner
BREAKING_EGGS = "breaking_some_eggs"
HARDCODED_BUY = re.compile(r"\(.*\)buy.gems", re.IGNORECASE)  # Guide nennt den Kauf schon selbst
QUEST_ITEM = re.compile(r"\(quest:([^)]*)\)")


@dataclass
class Segment:
    text: str = ""
    color: str = WHITE
    image: str = ""  # Symbol aus (img:…) statt Text
    layout: str = ""  # Name des Layout-Bilds zu diesem Begriff


@dataclass
class Line:
    segments: list[Segment]
    bullet: str = ""  # "", "step", "optional", "hint"


@dataclass
class Rendered:
    lines: list[Line] = field(default_factory=list)
    buy_gems: list[str] = field(default_factory=list)
    buy_items: list[str] = field(default_factory=list)


@dataclass
class Where:
    """Wo der Spieler gerade ist: Zonen anderer Akte bekommen den Akt vorangestellt."""
    act: int = 0  # 0 = unbekannt
    hideout: bool = False


class PageRenderer:
    def __init__(self, data: LevelingData, options: Options, layouts: set[str]) -> None:
        self.data = data
        self.options = options
        self.layouts = layouts  # Namen der Layout-Bilder mit Leerzeichen („opposite corners1“)

    def render(self, lines: list[str], where: Where) -> Rendered:
        out = Rendered()
        visible = [i for i in range(len(lines)) if self._shown(lines, i)]
        bullets = sum(HINT not in lines[i] for i in visible) > 1
        buy_at = -1  # hier kommt die Kaufzeile hin
        hardcoded = False
        for index in visible:
            line = lines[index]
            hardcoded = hardcoded or bool(HARDCODED_BUY.search(line))
            if self._collect_buy(line, out):
                buy_at = len(out.lines) if buy_at < 0 else buy_at
                continue
            segments = self._segments(self._clean(line), line, where)
            if segments:
                out.lines.append(Line(segments, self._bullet(line) if bullets else ""))
        if buy_at >= 0:
            out.lines.insert(buy_at, self._buy_line(out, bullets, hardcoded))
        return out

    # ------------------------------------------------------------ welche Zeilen
    def _shown(self, lines: list[str], index: int) -> bool:
        line = lines[index]
        if QUEST_CHECK in line or (not self.options.level_hints and any(h in line for h in LEVEL_HINTS)):
            return False
        return not self._filtered(line, _parent(lines, index))

    def _filtered(self, line: str, parent: str) -> bool:
        """Optionale, Ligastart- und Twink-Zeilen; Unterpunkte erben das von ihrer Zeile."""
        def has(tag: str) -> bool:
            return tag in line or tag in parent
        return ((not self.options.optionals and has(OPTIONAL)) or (not self.options.league_start and has(LEAGUE_START))
                or (self.options.league_start and has(TWINK)))

    @staticmethod
    def _bullet(line: str) -> str:
        if HINT in line:
            return "hint"
        return "optional" if OPTIONAL in line else "step"

    # ------------------------------------------------------------ Kaufen
    @staticmethod
    def _collect_buy(line: str, out: Rendered) -> bool:
        if BUY_GEM not in line and BUY_ITEM not in line:
            return False
        what = line[line.find(":") + 2:]
        if "(" in what:
            what = what[what.find(")") + 1:]
        (out.buy_items if BUY_ITEM in line else out.buy_gems).append(what.replace("_", " "))
        return True

    @staticmethod
    def _buy_line(out: Rendered, bullets: bool, hardcoded: bool) -> Line:
        """Was zu kaufen ist, mit Namen (das Original zeigte nur „buy gems“ und kaufte per Omni-Taste).
        Kündigt der Guide den Kauf selbst an, stehen die Namen als Unterpunkt darunter."""
        names = Segment(", ".join(out.buy_gems + out.buy_items))
        if hardcoded:
            return Line([names], "hint" if bullets else "")
        label = "buy items:" if out.buy_items else "buy gems:"
        return Line([Segment(f"{label} ", BUY_COLOR), names], "step" if bullets else "")

    # ------------------------------------------------------------ eine Zeile
    def _clean(self, line: str) -> list[str]:
        """Zeile in Wörter zerlegen, Satzzeichen als eigene Wörter."""
        if f"<{BREAKING_EGGS}1>" in line and f"<{BREAKING_EGGS}2>" in line:
            line = line.replace(f", <{BREAKING_EGGS}2>", "")
        lilly = line.find("|| lilly:")
        if lilly >= 0:
            line = line[:max(lilly - 1, 0)]
        for tag in TAGS:
            line = line.replace(f"{tag} ", "")
        line = strip_comment(line.replace(": ", " : ").replace(". ", " . ").replace(", ", " , "))
        for name in self.layouts:
            line = line.replace(name, name.replace(" ", "_"))
        return _words(line)

    def _segments(self, words: list[str], raw: str, where: Where) -> list[Segment]:
        segments: list[Segment] = []
        after_kill = False
        for index, word in enumerate(words):
            following = words[index + 1] if index + 1 < len(words) else ""
            if "(lvl:" in word:
                if not self.options.level_hints:
                    continue
                word = word.replace("lvl:", "")
            if "(img:" in word:
                segments.append(Segment(image=_inside(word, "(img:").replace(" ", "_")))
                continue
            previous = words[index - 1] if index else ""
            segment = self._word(word, raw, where)
            segment.color = _override(word, self._color(word, previous, after_kill), segment)
            if segment.layout:
                segment.color = LAYOUT_COLOR
            if not (following == "" or following[0] in NO_SPACE_BEFORE or "(img:" in following):
                segment.text += " "
            segments.append(segment)
            after_kill = word == KILL
        return segments

    def _word(self, word: str, raw: str, where: Where) -> Segment:
        text = word
        for remove in ("<", ">", "arena:", "(hint)"):
            text = text.replace(remove, "")
        if AREA in text:
            text = self._area_name(text.replace(AREA, ""), "img:waypoint" in raw, where)
        text = text.replace("_", " ").replace("(a11)", "(epilogue)")
        quest_item = QUEST_ITEM.search(text)
        if quest_item:
            text = text.replace(quest_item.group(0), quest_item.group(1))
        layout = next((name for name in self.layouts if name in word.replace("_", " ")), "")
        # Nummern hinter Layout-Bildern und Quests („<breaking_some_eggs1>“) sind nur Schlüssel
        if (layout or f"<{text.replace(' ', '_')}>" in word) and text[-1:].isdigit():
            text = text[:-1]
        return Segment(text, layout=layout)

    def _area_name(self, area_id: str, waypoint: bool, where: Where) -> str:
        area = self.data.areas.get(area_id.lower())
        if not area:
            return area_id
        name = area.map_name if waypoint and area.map_name else area.name
        other_act = where.act and area.act != where.act and "labyrinth" not in area_id
        return f"{ACT_NAMES[area.act]} | {name}" if other_act or where.hideout else name

    @staticmethod
    def _color(word: str, previous: str, after_kill: bool) -> str:
        if re.search(r"img:(arena|in-out2)", previous, re.IGNORECASE) and word != ",":
            return ARENA_COLOR
        if AREA in word:
            return AREA_COLOR
        if (after_kill and word not in NOT_KILLED) or "arena:" in word:
            return KILL_COLOR
        if "<" in word:
            return QUEST_COLOR
        if "(quest:" in word:
            return QUEST_ITEM_COLOR
        if "trial" in word or "_lab" in word:
            return LAB_COLOR
        return WHITE


def _override(word: str, color: str, segment: Segment) -> str:
    """„(color:RRGGBB)“ im Guide setzt die Farbe selbst (z. B. Gem-Farbe nach Attribut)."""
    if "(color:" not in word:
        return color
    own = _inside(word, "(color:")
    segment.text = segment.text.replace(f"(color:{own})", "")
    return own


def _inside(word: str, opener: str) -> str:
    rest = word[word.find(opener) + len(opener):]
    return rest[:rest.find(")")]


def _words(line: str) -> list[str]:
    words: list[str] = []
    for word in line.split(" "):
        if not word or (not words and word == ","):
            continue
        if not word.startswith("(") and word.endswith(")"):
            words += [word[:-1], ")"]
        else:
            words.append(word)
    return words


def _parent(lines: list[str], index: int) -> str:
    """Die Zeile, zu der ein Unterpunkt gehört (leer, wenn es keiner ist)."""
    parent = index
    while parent >= 0 and HINT in lines[parent]:
        parent -= 1
    if parent == index or parent < 0:
        return ""
    return lines[parent]
