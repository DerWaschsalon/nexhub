"""Build-Check-Auswertung: Ampel, häufigste Wahl, Zuerst. Nur erfundene Momentaufnahmen im Format aus aion2.py."""
from nexhub_api.evaluation import evaluate, fields


def snap(cp: int = 100_000, enchant: int = 15, grade: str = "Epic", subs: tuple[str, ...] = ("Attack Speed",),
         crit: int = 500, nodes: int = 80) -> dict:
    return {
        "profile": {"name": "Testheld", "combat_power": cp},
        "stats": [{"type": "ItemLevel", "name": "Item Level", "value": 2600},
                  {"type": "Critical", "name": "Crit", "value": crit}],
        "equipment": [{"slot_name": "MainHand", "name": "Testbogen", "grade": grade, "enchant": enchant, "exceed": 0,
                       "detail": {"main": [], "sub": [{"name": s, "value": "5%"} for s in subs],
                                  "stones": [], "godstones": [], "skills": []}}],
        "skills": [], "daevanion": [{"name": "Nezekan", "open_nodes": nodes}],
        "titles": {"equipped": [{"name": "Golden Glow", "category": "Attack"}]},
        "wing": {"name": "Testflügel", "enchant": 0}, "pet": None,
    }


def field(result: dict, area: str, slot: str, key: str) -> dict:
    return next(f for f in result["fields"] if (f["area"], f["slot"], f["key"]) == (area, slot, key))


def test_zahl_ampel_und_besser():
    group = [snap(enchant=15)] * 10 + [snap(enchant=12)] * 5
    f = field(evaluate(snap(enchant=10), group), "equipment", "MainHand", "enchant")
    assert (f["median"], f["better"], f["light"]) == (15, 15, "red")
    f = field(evaluate(snap(enchant=12), group), "equipment", "MainHand", "enchant")
    assert (f["better"], f["light"]) == (10, "yellow")
    assert field(evaluate(snap(enchant=15), group), "equipment", "MainHand", "enchant")["light"] == "green"


def test_auswahl_haeufigste_zwei():
    group = [snap(grade="Epic")] * 9 + [snap(grade="Unique")] * 4 + [snap(grade="Rare")] * 2
    f = field(evaluate(snap(grade="Rare"), group), "equipment", "MainHand", "grade")
    assert f["common"] == [{"value": "Epic", "count": 9}, {"value": "Unique", "count": 4}]
    assert (f["light"], f["better"]) == ("yellow", 9)
    assert field(evaluate(snap(grade="Unique"), group), "equipment", "MainHand", "grade")["light"] == "green"
    assert field(evaluate(snap(grade="Legend"), group), "equipment", "MainHand", "grade")["light"] == "red"


def test_zusatzwert_fehlt_den_die_meisten_haben():
    group = [snap(subs=("Attack Speed",))] * 12 + [snap(subs=("Move Speed",))] * 3
    result = evaluate(snap(subs=()), group)
    keys = {(f["slot"], f["key"]) for f in result["fields"]}
    assert ("MainHand", "sub:Attack Speed") in keys and ("MainHand", "sub:Move Speed") not in keys
    f = field(result, "equipment", "MainHand", "sub:Attack Speed")
    assert (f["mine"], f["better"], f["light"]) == (0, 12, "red")


def test_todo_fuenf_nach_besser_ohne_gruene():
    weak = snap(cp=80_000, enchant=10, grade="Rare", subs=(), crit=300, nodes=40)
    strong = [snap(cp=100_000 + i) for i in range(15)]
    result = evaluate(weak, strong)
    assert result["size"] == 15 and len(result["todo"]) == 5
    assert all(f["light"] != "green" for f in result["todo"])
    better = [f["better"] for f in result["todo"]]
    assert better == sorted(better, reverse=True)
    assert result["todo"][0]["area"] == "equipment"  # bei Gleichstand Ausrüstung zuerst


def test_fehlende_felder_sind_null():
    f = fields({"profile": {}, "stats": [], "equipment": [], "skills": [], "daevanion": [], "titles": {}})
    assert f[("profile", "", "combat_power")] == 0 and f[("wing", "", "name")] == "—"


def test_zusatzwert_erst_ab_zwei_dritteln():
    # mit echten Daten waren „8 von 15 haben Manastein HP“ nur Rauschen
    group = [snap(subs=("Crit",))] * 9 + [snap(subs=())] * 6
    keys = {f["key"] for f in evaluate(snap(subs=()), group)["fields"]}
    assert "sub:Crit" not in keys
    group = [snap(subs=("Crit",))] * 10 + [snap(subs=())] * 5
    assert "sub:Crit" in {f["key"] for f in evaluate(snap(subs=()), group)["fields"]}


def test_auswahl_ohne_mehrheit_ist_gruen():
    group = [snap(grade=g) for g in ("Epic", "Epic", "Epic", "Unique", "Unique", "Rare", "Legend", "Mythic", "A",
                                     "B", "C", "D", "E", "F", "G")]
    assert field(evaluate(snap(grade="Common"), group), "equipment", "MainHand", "grade")["light"] == "green"


def test_zuerst_ohne_kampfkraft_und_stufe():
    result = evaluate(snap(cp=80_000, enchant=10), [snap(cp=100_000 + i) for i in range(15)])
    assert all(f["area"] != "profile" for f in result["todo"])
