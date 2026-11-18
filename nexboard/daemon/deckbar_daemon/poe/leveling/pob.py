"""Path-of-Building-Code lesen: Klasse, Aufstieg, Bandit und die Gems aus den Skill-Sets.

Wie Leveltracker_PobImport im Original; der Passivbaum wird nicht gebraucht (die Leiste zeigt ihn nicht).
Ein PoB-Code ist ein zlib-gepacktes XML in URL-sicherem Base64; pobb.in liefert ihn unter <link>/raw.
"""
from __future__ import annotations

import base64
import binascii
import re
import xml.etree.ElementTree as ET
import zlib

from pydantic import BaseModel, Field

ASCENDANCIES = {
    "scion": ("ascendant", "reliquarian"),
    "marauder": ("juggernaut", "berserker", "chieftain"),
    "ranger": ("warden", "deadeye", "pathfinder"),
    "witch": ("occultist", "elementalist", "necromancer"),
    "duelist": ("slayer", "gladiator", "champion"),
    "templar": ("inquisitor", "hierophant", "guardian"),
    "shadow": ("assassin", "trickster", "saboteur"),
}
POBBIN = re.compile(r"^(?:https?://)?pobb\.in/[\w-]+/?$")
POB_TAGS = re.compile(r"\^x[0-9a-fA-F]{6}|\^\d|&[^;]{0,5};")  # Farbcodes und HTML-Entitäten in Titeln
PREFIXES = ("vaal ", "awakened ")


class PobError(ValueError):
    pass


class Gem(BaseModel):
    name: str
    support: bool = False

    @property
    def key(self) -> str:
        """Name, wie er in gems.json steht (Supports enden auf „support“)."""
        if self.support and "support" not in self.name:
            return f"{self.name} support"
        return self.name


class GemGroup(BaseModel):
    label: str = ""
    gems: list[Gem] = Field(default_factory=list)


class SkillSet(BaseModel):
    title: str = "default"
    groups: list[GemGroup] = Field(default_factory=list)


class PobBuild(BaseModel):
    char_class: str
    ascendancies: list[str] = Field(default_factory=list)
    bandit: str = "none"
    skill_sets: list[SkillSet] = Field(default_factory=list)


def is_pobbin(text: str) -> bool:
    return bool(POBBIN.match(text.strip()))


def pobbin_raw_url(link: str) -> str:
    link = link.strip().rstrip("/")
    return f"{link if link.startswith('http') else 'https://' + link}/raw"


def decode(code: str) -> str:
    """PoB-Code → XML; ungültig: PobError."""
    try:
        data = base64.b64decode(code.strip().replace("-", "+").replace("_", "/") + "===")
        return zlib.decompress(data).decode("utf-8")
    except (binascii.Error, zlib.error, UnicodeDecodeError) as e:
        raise PobError("Das ist kein Path-of-Building-Code") from e


def parse(xml_text: str, known_gem: set[str]) -> PobBuild:
    """XML aus PoB lesen. known_gem: Namen aus gems.json (für „X of Y“-Varianten)."""
    try:
        root = ET.fromstring(xml_text)
    except ET.ParseError as e:
        raise PobError("PoB-Daten sind beschädigt") from e
    build = root.find("Build")
    if root.tag != "PathOfBuilding" or build is None:
        raise PobError("Das ist kein Path-of-Building-Build")
    char_class = (build.get("className") or "").lower()
    return PobBuild(char_class=char_class, ascendancies=_ascendancies(root, char_class),
                    bandit=(build.get("bandit") or "none").lower(),
                    skill_sets=_skill_sets(root, known_gem))


def _clean(text: str) -> str:
    return POB_TAGS.sub("", text).lower()


def _ascendancies(root: ET.Element, char_class: str) -> list[str]:
    names = ASCENDANCIES.get(char_class, ())
    out: list[str] = []
    for spec in root.iter("Spec"):
        index = int(spec.get("ascendClassId") or 0)
        if 0 < index <= len(names) and names[index - 1] not in out:
            out.append(names[index - 1])
    return out or ["none"]


def _skill_sets(root: ET.Element, known_gem: set[str]) -> list[SkillSet]:
    skills = root.find("Skills")
    if skills is None:
        return []
    sets = skills.findall("SkillSet") or [skills]  # ältere PoB-Versionen: Skills ohne Sets
    out = []
    for skill_set in sets:
        groups = [_group(skill, known_gem) for skill in skill_set.iter("Skill")]
        groups = [g for g in groups if g.gems]
        if groups:
            out.append(SkillSet(title=_clean(skill_set.get("title") or "default"), groups=groups))
    return out


def _group(skill: ET.Element, known_gem: set[str]) -> GemGroup:
    gems = [_gem(element, known_gem) for element in skill.findall("Gem")]
    return GemGroup(label=_clean(skill.get("label") or ""), gems=[g for g in gems if g])


def _gem(element: ET.Element, known_gem: set[str]) -> Gem | None:
    name = (element.get("nameSpec") or "").lower()
    if not name:
        return None
    support = ("/supportgem" in (element.get("gemId") or "").lower()
               or "support" in (element.get("skillId") or "").lower())
    for prefix in PREFIXES:
        name = name.replace(prefix, "")
    name = name.split(":", 1)[0]
    # Transfigurierte Gems („Cleave of Rage“) gibt es zu kaufen wie das Grund-Gem
    base = name.split(" of ", 1)[0]
    if not support and " of " in name and base in known_gem:
        name = base
    return Gem(name=name, support=support)
