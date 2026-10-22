"""Charakterdaten von der offiziellen AION-2-Website, nach dem Vorbild von
github.com/nuriland/aion2-api (MIT).

Nur die Global-Server (NA, EU, SA, Asien): eine Website, der Parameter `region` wählt den Shard,
und die Server-ID verrät ihn (dritte Stelle von hinten: 2302 = EU). Taiwan und Korea haben eigene
Seiten, Korea sperrt Anfragen von außerhalb; beide fehlen hier.
"""
from __future__ import annotations

import asyncio
import re
from urllib.parse import unquote

import httpx

SITE = "https://aion2.plaync.com/api/character"
SEARCH = "https://api-search.plaync.com/aion2global/search/v2/character"
PROFILE_IMAGES = "https://profileimg.plaync.com"
# Jede Momentaufnahme gibt es in beiden Sprachen des Hubs; die Web-Oberfläche zeigt die passende
LANGS = {"de": "de-DE", "en": "en-US"}
FORMAT = 2  # data = {"v": 2, "de": {...}, "en": {...}}; ältere Momentaufnahmen sind ein Sprach-Objekt
SHARDS = {1: "nae", 2: "naw", 3: "eu", 4: "la", 5: "as"}
# Wie die aion2-api: die Seite antwortet Browsern
USER_AGENT = ("Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) "
              "Chrome/140.0.0.0 Safari/537.36")
TRIES = 3
_TAGS = re.compile(r"</?strong>")


class NCError(Exception):
    """NC antwortet nicht oder anders als erwartet. Der Text landet kurz in `run_characters.error`."""


class NotFound(NCError):
    """Diesen Charakter gibt es dort nicht (oder der Server wird nicht unterstützt)."""


def shard_of(server_id: int) -> str | None:
    return SHARDS.get(server_id // 100 % 10) if 1100 <= server_id < 2600 else None


def _lines(rows: object) -> list[str]:
    """NC schickt Effekt-Zeilen als [{"desc": "…"}], manchmal als Strings oder null."""
    if not isinstance(rows, list):
        return []
    return [r["desc"] if isinstance(r, dict) else str(r) for r in rows if r]


def _flag(v: object) -> bool:
    return v in (1, True, "1", "true")


def _pick(row: object, **fields: str) -> dict | None:
    return {k: row.get(src) for k, src in fields.items()} if isinstance(row, dict) else None


def _nodes(rows: object) -> list[dict]:
    """Knoten eines Daevanion-Bretts für die Darstellung wie im Spiel (Raster 15×15). Leere Felder
    (type None, rund 60 %) fallen weg; Typen Start, Stat, SkillLevel; Seltenheit wie bei Gegenständen.
    Den Namen lassen wir weg, er wiederholt nur den Effekt („Fäh.-Stufenaufstieg – Orkanpfeil“)."""
    if not isinstance(rows, list):
        return []
    return [{"row": n.get("row"), "col": n.get("col"), "type": n.get("type"), "grade": n.get("grade"),
             "open": _flag(n.get("open")), "effects": [e for e in _lines(n.get("effectList")) if e]}
            for n in rows if isinstance(n, dict) and n.get("type") not in (None, "None")]


def localized(data: dict, lang: str = "en") -> dict:
    """Die Momentaufnahme in einer Sprache – auch ältere ohne Sprachen (siehe FORMAT)."""
    if not data.get("v"):
        return data
    return data.get(lang) or data.get("en") or {}


def item_level(data: dict) -> int | None:
    return next((s["value"] for s in localized(data).get("stats", []) if s["type"] == "ItemLevel"), None)


def combat_power(data: dict) -> int | None:
    return (localized(data).get("profile") or {}).get("combat_power")


def _stats(rows: object, *fields: str) -> list[dict]:
    """Werte eines Gegenstands: [{name, value, …}] ohne leere Zeilen."""
    if not isinstance(rows, list):
        return []
    return [{"name": r.get("name"), "value": r.get("value"), **{f: r.get(f) for f in fields}}
            for r in rows if isinstance(r, dict) and r.get("name")]


def _item_detail(d: dict) -> dict:
    """Was ein Gegenstand im Spiel anzeigt: Grundwerte (+ Bonus aus Verzauberung), zufällige
    Zusatzwerte, Manasteine, Gottsteine, verstärkte Skills und bei Arkana das Set."""
    detail = {
        "level": d.get("level"), "category": d.get("categoryName"),
        "main": _stats(d.get("mainStats"), "extra"),
        "sub": _stats(d.get("subStats")),
        "stones": _stats(d.get("magicStoneStat"), "grade", "icon"),
        "godstones": [{"name": g.get("name"), "desc": g.get("desc"), "grade": g.get("grade"), "icon": g.get("icon")}
                      for g in d.get("godStoneStat") or [] if isinstance(g, dict)],
        "skills": [{"name": k.get("name"), "level": k.get("level"), "icon": k.get("icon")}
                   for k in d.get("subSkills") or [] if isinstance(k, dict)],
    }
    if isinstance(d.get("set"), dict):
        st = d["set"]
        detail["set"] = {"name": st.get("name"), "equipped": st.get("equippedCount") or 0,
                         "total": len(st.get("items") or []),
                         "bonuses": [{"degree": b.get("degree"), "lines": [x for x in b.get("descriptions") or [] if x]}
                                     for b in st.get("bonuses") or [] if isinstance(b, dict)]}
    return detail


class NC:
    def __init__(self, http: httpx.AsyncClient, pause: float = 0.3) -> None:
        self.http, self.pause = http, pause

    async def _get(self, url: str, params: dict) -> dict:
        """Eine Anfrage, nacheinander mit Pause; 5xx, 429 und Netzfehler bis zu dreimal."""
        error = NCError("keine Antwort")
        for _ in range(TRIES):
            await asyncio.sleep(self.pause)
            try:
                r = await self.http.get(url, params=params, headers={"user-agent": USER_AGENT}, timeout=10)
            except httpx.HTTPError as e:
                error = NCError(f"nicht erreichbar ({type(e).__name__})")
                continue
            if r.status_code >= 500 or r.status_code == 429:
                error = NCError(f"HTTP {r.status_code}")
                continue
            if r.status_code == 404:  # z. B. Gegenstand nicht (mehr) in diesem Slot
                raise NotFound("HTTP 404")
            if r.status_code >= 400:
                raise NCError(f"HTTP {r.status_code}")
            try:
                body = r.json()
            except ValueError:
                raise NCError("Format unbekannt: kein JSON") from None
            if not isinstance(body, dict):
                raise NCError("Format unbekannt: kein Objekt")
            return body
        raise error

    async def find(self, name: str, server_id: int) -> str:
        """Charakter-ID zu Name und Server. Namen sind je Server eindeutig."""
        shard = shard_of(server_id)
        if shard is None:
            raise NotFound("Server nicht unterstützt" if server_id else "Server unbekannt")
        body = await self._get(SEARCH, {"keyword": name, "page": 1, "size": 40, "serverId": server_id,
                                        "region": shard, "localeInfo": LANGS["en"]})
        rows = body.get("list")
        if not isinstance(rows, list):
            raise NCError("Format unbekannt: Suche ohne list")
        for row in rows:
            if (_TAGS.sub("", str(row.get("name", ""))).casefold() == name.casefold()
                    and row.get("serverId") == server_id and row.get("characterId")):
                return unquote(row["characterId"])
        raise NotFound("nicht gefunden")

    async def search(self, name: str, region: str) -> list[dict]:
        """Charaktere, deren Name `name` enthält, auf allen Servern einer Region (für die Armory)."""
        if region not in SHARDS.values():
            raise NotFound("Region nicht unterstützt")
        body = await self._get(SEARCH, {"keyword": name, "page": 1, "size": 20, "region": region,
                                        "localeInfo": LANGS["en"]})
        rows = body.get("list")
        if not isinstance(rows, list):
            raise NCError("Format unbekannt: Suche ohne list")
        hits = []
        for row in rows:
            if not (isinstance(row, dict) and row.get("characterId") and isinstance(row.get("serverId"), int)
                    and shard_of(row["serverId"])):
                continue
            image = str(row.get("profileImageUrl") or "")  # relativ zu PROFILE_IMAGES
            hits.append({"name": _TAGS.sub("", str(row.get("name", ""))), "server_id": row["serverId"],
                         "server": row.get("serverName"), "level": row.get("level"),
                         "character_id": unquote(row["characterId"]),
                         "image": PROFILE_IMAGES + image if image.startswith("/") else None})
        return hits

    async def item(self, server_id: int, character_id: str, lang: str, item: dict) -> dict | None:
        """Werte eines angelegten Gegenstands (_item_detail). None, wenn der Charakter ihn in diesem
        Slot nicht mehr trägt – so passen nachgeladene Werte immer zum gespeicherten Gegenstand."""
        if not item.get("id"):
            return None
        try:
            d = await self._get(f"{SITE}/equipment/item", {
                "lang": LANGS[lang], "region": shard_of(server_id), "serverId": server_id,
                "characterId": character_id, "id": item["id"], "enchantLevel": item.get("enchant") or 0,
                "slotPos": item.get("slot")})
        except NotFound:
            return None
        if not d.get("id") or not d.get("name"):
            return None
        return _item_detail(d)

    async def snapshots(self, server_id: int, character_id: str, items: bool = False) -> dict:
        """Momentaufnahme in allen Sprachen (FORMAT). `items`: dazu je Gegenstand die Werte – eine
        Anfrage mehr je Gegenstand und Sprache, deshalb nur für die Armory."""
        data: dict = {"v": FORMAT}
        for lang in LANGS:
            data[lang] = await self.snapshot(server_id, character_id, lang, items)
        return data

    async def snapshot(self, server_id: int, character_id: str, lang: str = "en", items: bool = False) -> dict:
        """Profil, Werte, Titel, Ausrüstung, Skills und Daevanion in einer Sprache, im gespeicherten Format."""
        q = {"lang": LANGS[lang], "region": shard_of(server_id), "serverId": server_id, "characterId": character_id}
        info = await self._get(f"{SITE}/info", q)
        profile = info.get("profile")
        if not isinstance(profile, dict):
            raise NCError("Format unbekannt: Profil fehlt")
        if not profile.get("characterId"):
            raise NotFound("nicht gefunden")
        equip = await self._get(f"{SITE}/equipment", q)
        if not isinstance(equip.get("equipment"), dict):
            raise NCError("Format unbekannt: Ausrüstung fehlt")

        boards = []
        for b in (info.get("daevanion") or {}).get("boardList") or []:
            is_open = _flag(b.get("open"))
            detail = await self._get(f"{SITE}/daevanion/detail", {**q, "boardId": b["id"]}) if is_open else {}
            boards.append({"id": b.get("id"), "name": b.get("name"), "icon": b.get("icon") or None,
                           "open": is_open, "open_nodes": b.get("openNodeCount") or 0,
                           "total_nodes": b.get("totalNodeCount") or 0,
                           "stats": _lines(detail.get("openStatEffectList")),
                           "skills": _lines(detail.get("openSkillEffectList")),
                           "nodes": _nodes(detail.get("nodeList"))})

        equipment = []
        for e in equip["equipment"].get("equipmentList") or []:
            item = {"id": e.get("id"), "slot": e.get("slotPos"), "slot_name": e.get("slotPosName"),
                    "name": e.get("name"), "grade": e.get("grade"), "enchant": e.get("enchantLevel") or 0,
                    "exceed": e.get("exceedLevel") or 0, "icon": e.get("icon") or None}
            if items:
                item["detail"] = await self.item(server_id, character_id, lang, item)
            equipment.append(item)

        titles = info.get("title") or {}
        petwing = equip.get("petwing") or {}
        return {
            "profile": _pick(profile, name="characterName", level="characterLevel", **{"class": "className"},
                             gender="genderName", race="raceId", server="serverName", guild="regionName",
                             title="titleName", combat_power="combatPower", image="profileImage"),
            "stats": [{"type": s.get("type"), "name": s.get("name"), "value": s.get("value"),
                       "effects": [e for e in s.get("statSecondList") or [] if e]}
                      for s in (info.get("stat") or {}).get("statList") or []],
            "titles": {"owned": titles.get("ownedCount"), "total": titles.get("totalCount"),
                       "equipped": [{"name": t.get("name"), "grade": t.get("grade"),
                                     "category": t.get("equipCategory"), "effects": _lines(t.get("equipStatList"))}
                                    for t in titles.get("titleList") or []]},
            "equipment": equipment,
            "pet": _pick(petwing.get("pet"), name="name", level="level", icon="icon"),
            "wing": _pick(petwing.get("wing"), name="name", grade="grade", enchant="enchantLevel", icon="icon"),
            "skills": [{"name": s.get("name"), "category": s.get("category"), "level": s.get("skillLevel") or 0,
                        "learned": _flag(s.get("acquired")), "equipped": _flag(s.get("equip")),
                        "icon": s.get("icon") or None}
                       for s in (equip.get("skill") or {}).get("skillList") or []],
            "daevanion": boards,
        }
