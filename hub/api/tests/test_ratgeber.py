"""Ratgeber der Armory: Hinweise aus einer Momentaufnahme, ohne Netz."""
from nexhub_api.ratgeber import hints


def item(slot: str = "MainHand", **detail) -> dict:
    return {"slot_name": slot, "name": f"Teil {slot}", "icon": None, "grade": "Unique",
            "detail": {"stones": [], "sub": [], **detail}}


def stone(sid: str, name: str, value: str = "+6") -> dict:
    return {"id": sid, "name": name, "value": value}


def test_reihenfolge_von_schnell_bis_teuer():
    snap = {"equipment": [
        item("MainHand", gain={"enchant": 20, "stats": [{"name": "Angriffskraft", "value": "+34"}]},
             stones=[stone("Critical", "Krit"), stone("MPMax", "MP")], stone_slots=3,
             sub=[stone("Block", "Blocken", "4%"), stone("AdditionalHitRate", "Mehrfachtreffer", "9%")]),
    ]}
    out = hints(snap, "ranger")
    assert [h["art"] for h in out] == ["sockel", "verzaubern", "stein", "nebenwert"]
    assert out[0]["frei"] == 1
    assert out[1] == {"art": "verzaubern", "slot": "MainHand", "item": "Teil MainHand", "icon": None,
                      "grade": "Unique", "stufe": 20, "werte": ["Angriffskraft +34"]}
    assert out[2]["werte"] == ["MP +6"] and out[3]["werte"] == ["Blocken 4%"]


def test_tank_und_heiler_ohne_wertepruefung():
    snap = {"equipment": [item(stones=[stone("ArmorDefense", "Verteidigung")], stone_slots=1)]}
    assert hints(snap, "templar") == []
    assert [h["art"] for h in hints(snap, "ranger")] == ["stein"]


def test_arkana_set_ohne_bonus_einmal():
    bonus = {"name": "Testset", "equipped": 1, "total": 5, "bonuses": [{"degree": 2, "lines": []}]}
    snap = {"equipment": [item("Arcana1", set=bonus), item("Arcana2", set=bonus)]}
    assert hints(snap, "ranger") == [{"art": "set", "set": "Testset", "hat": 1, "braucht": 2}]
    bonus["equipped"] = 2
    assert hints(snap, "ranger") == []


def test_alte_staende_ohne_werte():
    assert hints({"equipment": [{"slot_name": "MainHand", "name": "x", "detail": None}]}, "ranger") == []
    assert hints({}, None) == []
