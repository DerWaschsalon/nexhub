"""Bewertung der Ausrüstung (rating.py): Zählung, Note, ideale Zeilen.
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


def wide_census() -> rating.Census:
    """Top-Spieler tragen einen Schild mit sechs Werten und einem Skill, das eigene Teil hat nur vier Zeilen."""
    wide = shield(("Combat Speed", "12.3%"), ("Weapon Damage Boost", "7.3%"), ("Might", "25"),
                  ("Multi-hit Chance", "9.1%"), ("Damage Boost", "5.5%"), ("Critical Hit", "61"))
    wide["detail"]["skills"] = [{"name": "Testschuss", "level": 2}]
    data = rating.add_tops({"slots": rating.count_players([[wide]] * 10)}, {SLOT: {"Testschild"}},
                           {"Testschild": TABLE}, "ranger")
    return rating.Census(data["slots"], data["tops"])


def test_bestes_stueck_haengt_nicht_am_eigenen_teil():
    c = wide_census()
    assert c.slots[SLOT]["width"] == [6, 1] and c.slots[SLOT]["skills"] == ["Testschuss"]
    # sechs Werte und ein Skill, alle bei jedem Top-Spieler
    assert c.best_piece(SLOT) == 7.0
    # vier volle ideale Zeilen sind vier Siebtel des besten Stücks, nicht 100
    value, _ = rating.score(c, TOP, TABLE, "ranger")
    assert value == round(100 * 4 / 7, 1)


def test_teile_eines_platzes_sind_vergleichbar():
    c = wide_census()
    five = shield(("Combat Speed", "12.3%"), ("Weapon Damage Boost", "7.3%"), ("Might", "25"),
                  ("Multi-hit Chance", "9.1%"), ("Damage Boost", "5.5%"))
    assert rating.score(c, five, TABLE, "ranger")[0] > rating.score(c, TOP, TABLE, "ranger")[0]


def test_alte_zaehlung_ohne_breite_gibt_keine_note():
    data = census()
    del data["slots"][SLOT]["width"]
    assert rating.rate(data, {"Testschild": TABLE}, {"equipment": [MINE]}, None, "ranger", "en")["items"] == []


def test_idealteil_mit_haken():
    c = rating.Census(census()["slots"], census()["tops"])
    ideal = rating.ideal_piece(c, MINE, TABLE, "ranger")
    # die vier häufigsten Zeilen des Platzes nach Priorität; MINE hat zwei davon
    assert [line["name"] for line in ideal] == ["Might", "Weapon Damage Boost", "Combat Speed", "Multi-hit Chance"]
    assert [line["have"] for line in ideal] == [True, True, False, False]
    assert ideal[2] == {"name": "Combat Speed", "share": 0.9, "max": 12.3, "have": False}


def test_ausgabe_deutsch():
    me_en = {"equipment": [MINE]}
    me_de = {"equipment": [shield(("Schadensverstärkung", "5.5%"), ("Macht", "25"), ("Kritischer Treffer", "44"),
                                  ("Verstärkung (Waffenschaden)", "6.3%"))]}
    out = rating.rate(census(), {"Testschild": TABLE}, me_en, me_de, "ranger", "de")
    item = out["items"][0]
    assert out["size"] == 10 and out["group"] == "EU · Testraid · Hard"
    assert [ln["name"] for ln in item["lines"]][2] == "Kritischer Treffer"
    assert item["source"] == TABLE["url"]
    # Idealteil: Namen vom eigenen Teil, sonst aus der Würfeltabelle
    assert (item["ideal"], item["ideal_of"]) == (2, 4)
    assert [line["name"] for line in item["ideal_piece"]][-2:] == ["Kampftempo", "Mehrfachtreffer"]


def test_ohne_wuerfeltabelle_keine_note():
    out = rating.rate(census(), {}, {"equipment": [MINE]}, None, "ranger", "en")
    assert out["items"] == []
