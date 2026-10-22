"""Nachgebaute AION-2-Website für Tests: Antworten im Format der echten, Inhalte erfunden."""
from __future__ import annotations

from urllib.parse import parse_qs

import httpx

HOSTS = {"aion2.plaync.com", "api-search.plaync.com"}
ICON = "https://assets.playnccdn.com/static-aion2-gamedata/resources/Icon_WP_BW_0028_T05.png"


def search_row(name: str, server: int = 2302, cid: str = "abc%3D", pc: int = 16) -> dict:
    return {"characterId": cid, "name": f"<strong>{name}</strong>", "race": 2, "pcId": pc, "level": 45,
            "serverId": server, "serverName": "Zikel", "region": "eu",
            "profileImageUrl": f"/game_profile_images/aion2global/images?gameServerKey={server}&charKey=1"}


def info(name: str = "Testheld") -> dict:
    return {
        "profile": {"characterId": "abc%3D", "characterName": name, "characterLevel": 45, "pcId": 16,
                    "className": "Waldläufer", "genderName": "Weiblich", "raceId": 2, "serverName": "Zikel",
                    "regionName": "Testgilde", "combatPower": 123456, "titleName": "Füttere mich!",
                    "profileImage": "https://profileimg.plaync.com/game_profile_images/aion2global/images?charKey=1"},
        "stat": {"statList": [
            {"type": "STR", "name": "Macht", "value": 36, "statSecondList": ["Angriffskraft + +3.6%"]},
            {"type": "ItemLevel", "name": "아이템레벨", "value": 2554, "statSecondList": None}]},
        "title": {"totalCount": 297, "ownedCount": 206, "titleList": [
            {"id": 1, "name": "Goldener Glanz", "grade": "Unique", "equipCategory": "Attack", "totalCount": 103,
             "ownedCount": 74, "ownedPercent": 72, "statList": [{"desc": "Krit.-Angriffskraft +3"}],
             "equipStatList": [{"desc": "Krit.-Angriffskraft +45"}]}]},
        "ranking": {"rankingList": []},
        "daevanion": {"boardList": [
            {"id": 31, "name": "Nezekan", "icon": "https://assets.playnccdn.com/static-aion2-gamedata/resources/UT_Sword.png",
             "open": 1, "openNodeCount": 64, "totalNodeCount": 88, "openPercent": 73},
            {"id": 36, "name": "Azphel", "icon": "", "open": 0, "openNodeCount": 0, "totalNodeCount": 152,
             "openPercent": 0}]},
    }


def equipment() -> dict:
    return {
        "equipment": {
            "equipmentList": [{"slotPos": 1, "slotPosName": "MainHand", "id": 110430050, "name": "Testbogen",
                               "grade": "Unique", "enchantLevel": 15, "exceedLevel": 1, "icon": ICON}],
            "skinList": [{"slotPos": 13, "slotPosName": "Bow", "id": 10033104, "name": "Hübscher Bogen",
                          "grade": "Legend", "enchantLevel": 0, "exceedLevel": 0, "icon": ICON}]},
        "petwing": {"pet": {"id": 1044, "name": "Testeule", "level": 1, "icon": ICON},
                    "wing": {"id": 4010, "name": "Testflügel", "grade": "Unique", "enchantLevel": 0, "icon": ICON},
                    "wingSkin": None},
        "skill": {"skillList": [
            {"id": 14010000, "name": "Zielpfeil", "category": "Active", "skillLevel": 17, "needLevel": 14,
             "acquired": 1, "equip": 1, "icon": ICON},
            {"id": 14060000, "name": "Greifenpfeil", "category": "Dp", "skillLevel": 0, "needLevel": 22,
             "acquired": 0, "equip": 1, "icon": ICON}]},
    }


def board() -> dict:
    return {"nodeList": [{"boardId": 31, "nodeId": 310004, "name": "", "grade": "None", "type": "None", "icon": "",
                          "row": 1, "col": 4, "open": 0, "effectList": []},
                         {"boardId": 31, "nodeId": 310113, "name": "Nezekan – Start", "grade": "None", "type": "Start",
                          "icon": "", "row": 8, "col": 8, "open": 0, "effectList": [{"desc": ""}]},
                         {"boardId": 31, "nodeId": 310037, "name": "Fäh.-Stufenaufstieg – Orkanpfeil", "grade": "Rare",
                          "type": "SkillLevel", "icon": "", "row": 3, "col": 7, "open": 1,
                          "effectList": [{"desc": "Orkanpfeil +1"}]},
                         {"boardId": 31, "nodeId": 310038, "name": "LP", "grade": "Common", "type": "Stat", "icon": "",
                          "row": 3, "col": 8, "open": 0, "effectList": [{"desc": "LP +600"}]}],
            "openSkillEffectList": [{"desc": "Orkanpfeil +1"}],
            "openStatEffectList": [{"desc": "LP +600"}]}


def item(name: str = "Testbogen") -> dict:
    """Werte eines angelegten Gegenstands (/api/character/equipment/item), gekürzt."""
    return {"id": 110430050, "name": name, "grade": "Unique", "level": 86, "categoryName": "Bogen",
            "mainStats": [{"id": "WeaponFixingDamage", "name": "Angriffskraft", "minValue": "354", "value": "486",
                           "extra": "146", "exceed": False}],
            "subStats": [{"id": "AdditionalHitRate", "name": "Mehrfachtreffer-Chance", "value": "9.1%"}],
            "magicStoneStat": [{"id": "Critical", "icon": ICON, "value": "+6", "name": "Kritischer Treffer",
                                "grade": "Legend", "slotPos": 0}],
            "godStoneStat": [{"icon": ICON, "name": "Gottstein: Test", "desc": "10 % Chance auf Wind-Schaden",
                              "grade": "Rare", "slotPos": 0}],
            "subSkills": [{"id": 1, "level": 2, "icon": ICON, "name": "Zielpfeil"}],
            "set": {"id": "Arcana_A_set_001", "name": "Testset", "equippedCount": 3,
                    "items": [{"id": 1}, {"id": 2}, {"id": 3}, {"id": 4}, {"id": 5}],
                    "bonuses": [{"degree": 2, "descriptions": ["Angriffskraft (PvE) +60"]}]}}


def pcdata() -> dict:
    """Klassentabelle der Website: je Klasse vier pcIds (Geschlecht × Rasse); hier nur drei Klassen."""
    classes = {13: "RANGER", 21: "ELEMENTALIST", 29: "CLERIC"}
    return {"pcDataList": [{"id": first + i, "className": name, "classText": name.title()}
                           for first, name in classes.items() for i in range(4)]}


class FakeNC:
    """Beantwortet Suche, Profil, Ausrüstung und Daevanion. `routes` lässt sich je Test überschreiben:
    Pfad → Antwort (dict = JSON 200, int = Statuscode, Exception = wird geworfen)."""

    def __init__(self) -> None:
        self.calls: list[str] = []
        self.langs: list[str] = []  # lang jeder Profil-/Ausrüstungs-/Gegenstandsanfrage
        self.rows = [search_row("Testheld")]
        self.routes: dict[str, object] = {}
        # Charakter-IDs, für die das Profil mit 500 antwortet (Fehler nur bei einem Spieler)
        self.fail_for: set[str] = set()
        # Build-Check: Kampfkraft je Charakter-ID im Profil, abgefragte IDs für Profil und Gegenstände
        self.cp_for: dict[str, int] = {}
        self.snapshot_ids: list[str] = []
        self.item_ids: list[str] = []

    def __call__(self, request: httpx.Request) -> httpx.Response:
        path = request.url.path
        self.calls.append(path)
        q = {k: v[0] for k, v in parse_qs(request.url.query.decode()).items()}
        if path.startswith("/api/character/"):
            self.langs.append(q.get("lang", ""))
        if path == "/api/character/info" and q.get("characterId") in self.fail_for:
            return httpx.Response(500)
        if path == "/api/character/info":
            self.snapshot_ids.append(q.get("characterId", ""))
        if path == "/api/character/equipment/item":
            self.item_ids.append(q.get("characterId", ""))
        pc_ids = q["pcId"].split(",") if "pcId" in q else None  # Klassenfilter der Suche
        found = [r for r in self.rows if q.get("keyword", "").lower() in r["name"].lower()
                 and (pc_ids is None or str(r["pcId"]) in pc_ids)]
        default = {
            "/en-us/api/gameinfo/pcdata": pcdata(),
            "/aion2global/search/v2/character": {"list": found,
                                                  "pagination": {"page": 1, "size": 40, "total": 1, "endPage": 1}},
            "/api/character/info": info(),
            "/api/character/equipment": equipment(),
            "/api/character/daevanion/detail": board(),
            "/api/character/equipment/item": item(),
        }
        if path == "/api/character/info" and q.get("characterId") in self.cp_for:
            default[path]["profile"]["combatPower"] = self.cp_for[q["characterId"]]
        answer = self.routes.get(path, default.get(path, 404))
        if isinstance(answer, Exception):
            raise answer
        if isinstance(answer, int):
            return httpx.Response(answer)
        return httpx.Response(200, json=answer)
