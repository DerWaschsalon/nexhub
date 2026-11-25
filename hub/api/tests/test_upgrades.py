"""Upgrade-Plan (upgrades.py): Zielnote, wenigste Versuche, Stufen der Ziele, Gruppen. Nur erfundene Daten,
derselbe Schild wie in test_rating.py."""
from nexhub_api.modules.armory import upgrades
from nexhub_api.modules.bis import rating

from .test_rating import MINE, SLOT, TABLE, TOP, census, shield

ROLLS = {"Testschild": TABLE}
# knapp unter S+: zwei ideale Zeilen, Krit niedrig gewürfelt, LP trägt kein Top-Spieler
CLOSE = shield(("Might", "25"), ("Weapon Damage Boost", "7.3%"), ("HP", "400"), ("Critical Hit", "44"))
# weit unter S+: nur eine ideale Zeile
WEAK = shield(("Might", "25"), ("HP", "400"), ("Critical Hit", "61"), ("Damage Boost", "5.5%"))


def planner(goal: str = "S+") -> upgrades.Planner:
    data = census()
    return upgrades.Planner(rating.Census(data["slots"], data["tops"]), "ranger", goal)


def test_ziel_ist_s_plus_und_die_note_stimmt_auch_bei_pech():
    card = planner().card(WEAK, TABLE)
    assert card is not None and card.now < 55 <= card.low <= card.mean <= card.high


def test_so_wenige_zeilen_wie_noetig():
    close, weak = planner().card(CLOSE, TABLE), planner().card(WEAK, TABLE)
    # knapp drunter: eine Zeile, und fast jeder Wurf reicht; weit drunter: zwei Zeilen
    assert [s.line for s in close.steps] == ["HP"] and close.tries < 1.5
    assert len(weak.steps) == 2 and weak.tries > close.tries


def test_schon_auf_zielnote_oder_zu_weit_weg():
    assert planner().card(TOP, TABLE) is None
    assert planner("BiS").card(WEAK, TABLE) is None  # drei Würfe reichen nicht für BiS


def test_ziele_nur_was_nicht_schon_drauf_ist():
    card = planner().card(WEAK, TABLE)
    names = {t.name for step in card.steps for t in step.targets}
    assert names == {"Combat Speed", "Multi-hit Chance", "Weapon Damage Boost"}  # der Rest ist schon drauf
    # zwei Zeilen werden nicht dasselbe: Dem zweiten Schritt fehlt das wahrscheinlichste Ziel des ersten
    assert sorted(len(step.targets) for step in card.steps) == [2, 3]


CLOSE_BOOTS = {**CLOSE, "slot_name": "Boots", "name": "Teststiefel"}


def test_gruppen_und_sortierung():
    en = {"equipment": [WEAK, CLOSE_BOOTS, {**TOP, "slot_name": "MainHand", "name": "Testbogen"}]}
    data = census()
    for slot in ("MainHand", "Boots"):
        data["slots"][slot], data["tops"][slot] = data["slots"][SLOT], data["tops"][SLOT]
    out = upgrades.plan(data, {**ROLLS, "Testbogen": TABLE, "Teststiefel": TABLE}, en, None, "ranger", "en")
    assert {c["slot"] for c in out["cards"]} == {SLOT, "Boots"} and [p["slot"] for p in out["done"]] == ["MainHand"]
    assert out["cards"][0]["per_try"] > out["cards"][1]["per_try"]  # „als Nächstes“ bringt je Versuch am meisten
    card = next(c for c in out["cards"] if c["slot"] == SLOT)
    assert card["after_letter"] == "S+" and card["after"][0] <= card["mean"] <= card["after"][1]
    step = card["steps"][0]
    assert step["tries"] == round(100 / step["chance"], 1) and not step["skill_only"]
    assert "best" in step["tiers"]


def test_ohne_wuerfeltabelle_nicht_erreichbar():
    out = upgrades.plan(census(), {}, {"equipment": [MINE]}, None, "ranger", "en")
    assert out["cards"] == [] and out["unreachable"] == [
        {"slot": SLOT, "name": "Testschild", "icon": None, "grade": None, "score": None, "letter": None,
         "reason": "no_rolls"}]


def test_nur_noch_binden():
    # dieselben idealen Zeilen wie TOP, aber niedrig gewürfelt und erst halb gebunden
    low = shield(("Combat Speed", "5%"), ("Weapon Damage Boost", "3%"), ("Might", "10"), ("Multi-hit Chance", "4%"))
    low["detail"]["soul_bind_rate"] = "50"  # als Text, wie die NC-API sie liefert
    out = upgrades.plan(census(), ROLLS, {"equipment": [low]}, None, "ranger", "en")
    assert [p["slot"] for p in out["bind"]] == [SLOT] and out["cards"] == []
    for rate in ("100", "", None):  # voll gebunden oder unbekannt: nicht „nur noch binden“
        low["detail"]["soul_bind_rate"] = rate
        out = upgrades.plan(census(), ROLLS, {"equipment": [low]}, None, "ranger", "en")
        assert out["bind"] == [] and len(out["cards"]) + len(out["unreachable"]) == 1, rate


def test_deutsche_namen():
    de = {"equipment": [shield(("Macht", "25"), ("LP", "400"), ("Kritischer Treffer", "61"),
                               ("Schadensverstärkung", "5.5%"))]}
    out = upgrades.plan(census(), ROLLS, {"equipment": [WEAK]}, de, "ranger", "de")
    step = out["cards"][0]["steps"][0]
    assert step["line"] in ("LP", "Kritischer Treffer", "Schadensverstärkung")
    assert "Kampftempo" in [t["name"] for tier in step["tiers"].values() for t in tier]
