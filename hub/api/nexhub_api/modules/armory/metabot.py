"""Würfeltabellen der Seelenbindung von MetaBot.GG (metabot.gg/en/aion-2/items/<name>).

Je Gegenstand: welche Werte gewürfelt werden können (Bereich und Chance) und welche Skills je Klasse
(Chance, höchste Stufe). NC verrät das nicht. MetaBot erlaubt die Weiterverwendung mit Link auf die
Seite und in ruhigem Tempo (Nutzungsbedingungen, „Data Usage & Attribution“): die Armory verlinkt
die Seite (`url`), census.py fragt höchstens alle paar Sekunden und je Gegenstand einmal pro Woche.

Die Seiten gibt es auch deutsch (/de_DE/), Zeilen in derselben Reihenfolge; daraus kommen `name_de`.
"""
from __future__ import annotations

import html
import re

import httpx

HOST = "metabot.gg"
PAGE = {"en": f"https://{HOST}/en/aion-2/items/", "de": f"https://{HOST}/de_DE/aion-2/items/"}
USER_AGENT = "NexHub (github.com/DerWaschsalon/nexhub)"
_NUMBER = re.compile(r"-?\d+(?:\.\d+)?")


class MetaBotError(Exception):
    pass


def slug(name: str) -> str:
    """Englischer Gegenstandsname → Adresse bei MetaBot („Hunter's Ring“ → „hunters-ring“)."""
    plain = name.lower().replace("'", "").replace("’", "")
    return re.sub(r"[^a-z0-9]+", "-", plain).strip("-")


def _text(fragment: str) -> str:
    return html.unescape(re.sub(r"<[^>]+>", "", fragment)).strip()


def _number(text: str) -> float:
    found = _NUMBER.search(text.replace(",", ""))
    return float(found.group()) if found else 0.0


def _rolls(page: str) -> tuple[int, list[dict]]:
    """Tabelle „Random stats (N rolls)“: Name, Bereich, Chance je Zeile."""
    found = re.search(r"\((\d+) [^)]*\)</h3>\s*<div[^>]*><table class=\"[^\"]*B32I9a_grid[^\"]*\">(.*?)</table>",
                      page, re.DOTALL)
    if not found:
        return 0, []
    rows = []
    for name, span, chance in re.findall(r'<tr><th scope="row">(.*?)</th><td[^>]*>(.*?)</td><td>(.*?)</td></tr>',
                                         found.group(2), re.DOTALL):
        low, high = (_number(part) for part in _text(span).split("–"))
        rows.append({"name": _text(name), "min": low, "max": high, "unit": "%" if "%" in span else "",
                     "chance": _number(_text(chance))})
    return int(found.group(1)), rows


def _skills(page: str) -> dict[str, dict]:
    """Skill-Optionen je Klasse: höchste Stufe und je Skill die Chance („8.33% each“ oder je Skill)."""
    start = page.find('data-section="skill-options"')
    if start < 0:
        start = page.find("Random skill options")
    if start < 0:
        start = page.find("Zufällige Fertigkeitsoptionen")
    if start < 0:
        return {}
    table = page[start:page.find("</table>", start)]
    out = {}
    for head, chips in re.findall(r'<tr><th scope="row"><span>(.*?)</span></th><td>(.*?)</td></tr>', table, re.DOTALL):
        info = _text(head)
        each = re.search(r"([\d.]+)\s?%", info)
        level = re.search(r"(\d+)\s*$", info)
        options = []
        for chip in chips.split('<span class="_8z5TwW_skillChip">')[1:]:
            name = re.search(r'class="B32I9a_nameText">(.*?)</span>', chip)
            own = re.search(r'class="_8z5TwW_sub">([\d.]+)%', chip)
            if name:
                chance = _number(own.group(1)) if own else (_number(each.group(1)) if each else 0.0)
                options.append({"name": _text(name.group(1)), "chance": chance})
        out[_text(head.split("<span", 1)[0])] = {"max_level": int(level.group(1)) if level else 1, "options": options}
    return out


def parse(page: str) -> dict:
    """Eine Gegenstandsseite → {roll_count, rolls, skills}; Skills je Klasse unter dem Anzeigenamen."""
    count, rolls = _rolls(page)
    return {"roll_count": count, "rolls": rolls, "skills": _skills(page)}


def merge(en: dict, de: dict) -> dict:
    """Deutsche Namen dazu: gleiche Reihenfolge der Zeilen und Skills auf beiden Seiten."""
    for row, row_de in zip(en["rolls"], de["rolls"]):
        row["name_de"] = row_de["name"]
    for opts, opts_de in zip(en["skills"].values(), de["skills"].values()):
        for o, o_de in zip(opts["options"], opts_de["options"]):
            o["name_de"] = o_de["name"]
    # Klassen unter dem Schlüssel des Hubs („Ranger“ → „ranger“)
    en["skills"] = {cls.lower(): v for cls, v in en["skills"].items()}
    return en


async def _page(http: httpx.AsyncClient, url: str) -> str:
    try:
        r = await http.get(url, headers={"user-agent": USER_AGENT}, timeout=30, follow_redirects=True)
    except httpx.HTTPError as e:
        raise MetaBotError(f"MetaBot nicht erreichbar ({type(e).__name__})") from e
    if r.status_code == 404:
        raise MetaBotError("Gegenstand bei MetaBot nicht gefunden")
    if r.status_code >= 400:
        raise MetaBotError(f"MetaBot: HTTP {r.status_code}")
    return r.text


async def item(http: httpx.AsyncClient, name: str) -> dict:
    """Würfeltabelle eines Gegenstands (englischer Name) samt deutscher Namen und Quellen-Link."""
    url = PAGE["en"] + slug(name)
    data = merge(parse(await _page(http, url)), parse(await _page(http, PAGE["de"] + slug(name))))
    data["url"] = url
    return data
