"""Bewertung der Ausrüstung (rating.py): Zählung, Note, ideale Zeilen, Weg zu Best in Slot.
Nur erfundene Daten, gebaut nach dem Muster eines Schilds mit Krit statt Kampftempo."""
from nexhub_api import rating

SLOT = "SubHand"
# Würfeltabelle des Schilds wie von metabot.py: Name, Bereich, Chance
TABLE = {"url": "https://metabot.gg/en/aion-2/items/testschild", "roll_count": 4, "skills": {}, "rolls": [
    {"name": "Combat Speed", "min": 10.6, "max": 12.3, "unit": "%", "chance": 4.0, "name_de": "Kampftempo"},
    {"name": "Weapon Damage Boost", "min": 6.4, "max": 7.3, "unit": "%", "chance": 4.0},
    {"name": "Might", "min": 21, "max": 25, "unit": "", "chance": 6.0},
    {"name": "Multi-hit Chance", "min": 7.9, "max": 9.1, "unit": "%", "chance": 6.0, "name_de": "Mehrfachtreffer"},
    {"name": "Damage Boost", "min": 5.0, "max": 5.5, "unit": "%", "chance": 2.0},
    {"name": "Critical Hit", "min": 50, "max": 61, "unit": "", "chance": 28.0},
    {"name": "HP", "min": 300, "max": 400, "unit": "", "chance": 50.0},
]}


def shield(*subs: tuple[str, str]) -> dict:
    return {"slot_name": SLOT, "name": "Testschild", "detail": {"sub": [{"name": n, "value": v} for n, v in subs],
                                                                 "skills": []}}


TOP = shield(("Combat Speed", "12.3%"), ("Weapon Damage Boost", "7.3%"), ("Might", "25"), ("Multi-hit Chance", "9.1%"))
MINE = shield(("Damage Boost", "5.5%"), ("Might", "25"), ("Critical Hit", "44"), ("Weapon Damage Boost", "6.3%"))


def census() -> dict:
    # neun Top-Spieler mit dem idealen Schild, einer mit Krit und Damage Boost
    players = [[TOP]] * 9 + [[shield(("Critical Hit", "61"), ("Damage Boost", "5.5%"), ("Might", "25"),
                                     ("Weapon Damage Boost", "7.3%"))]]
    data = {"slots": rating.count_players(players), "group": "EU · Testraid · Hard"}
    return rating.add_tops(data, {SLOT: {"Testschild"}}, {"Testschild": TABLE}, "ranger")


def test_zaehlung_ohne_namen():
    data = census()
    assert data["slots"][SLOT]["players"] == 10
    assert data["slots"][SLOT]["lines"]["Combat Speed"] == 9
    assert data["slots"][SLOT]["lines"]["Critical Hit"] == 1
    assert data["tops"][SLOT]["Combat Speed"] == 12.3


def test_ideales_stueck_ist_bis():
    c = rating.Census(census()["slots"], census()["tops"])
    value, lines = rating.score(c, TOP, TABLE, "ranger")
    assert value >= 90 and rating.letter(value) == "BiS"
    assert lines[0]["max"] == 12.3 and lines[0]["share"] == 0.9


def test_krit_wird_zu_kampftempo():
    c = rating.Census(census()["slots"], census()["tops"])
    up = rating.upgrade(c, MINE, TABLE, "ranger")
    first = up["steps"][0]
    assert first["line"]["name"] == "Critical Hit"
    # die fehlenden idealen Zeilen nach Priorität, Kampftempo und Mehrfachtreffer
    assert [g["name"] for g in first["best"]] == ["Combat Speed", "Multi-hit Chance"]
    assert 0 < first["chance"] < 100
    assert up["after"][0] > rating.score(c, MINE, TABLE, "ranger")[0]


def test_ideal_auch_wenn_die_note_schon_gut_ist():
    c = rating.Census(census()["slots"], census()["tops"])
    value, _ = rating.score(c, MINE, TABLE, "ranger")
    assert 35 <= value < 90  # gut benotet, aber kein BiS: trotzdem ein Weg zu Best in Slot
    assert rating.upgrade(c, MINE, TABLE, "ranger") is not None
    assert rating.upgrade(c, TOP, TABLE, "ranger") is None


def test_ausgabe_deutsch():
    me_en = {"equipment": [MINE]}
    me_de = {"equipment": [shield(("Schadensverstärkung", "5.5%"), ("Macht", "25"), ("Kritischer Treffer", "44"),
                                  ("Verstärkung (Waffenschaden)", "6.3%"))]}
    out = rating.rate(census(), {"Testschild": TABLE}, me_en, me_de, "ranger", "de")
    item = out["items"][0]
    assert out["size"] == 10 and out["group"] == "EU · Testraid · Hard"
    assert [l["name"] for l in item["lines"]][2] == "Kritischer Treffer"
    step = item["upgrade"]["steps"][0]
    assert step["line"] == "Kritischer Treffer"
    assert [t["name"] for t in step["tiers"]["best"]] == ["Kampftempo", "Mehrfachtreffer"]
    assert item["source"] == TABLE["url"]


def test_ohne_wuerfeltabelle_keine_note():
    out = rating.rate(census(), {}, {"equipment": [MINE]}, None, "ranger", "en")
    assert out["items"] == []
