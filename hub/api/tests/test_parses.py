"""Parses: Rechnung (calc.py), Abruf der Ranglisten (fetcher.py), Routen (routes.py)."""
from nexhub_api.modules.parses.calc import guild_bests, needed_pairs, percentile


def boss(mob: int, players: list[tuple[str, str | None, float]], killed: bool = True, fight: str = "f1") -> dict:
    return {"fight": fight, "name": f"Boss {mob}", "mob": mob, "start_ms": 0, "duration_ms": 120_000,
            "killed": killed, "players": [{"name": n, "cls": c, "damage": int(d * 120), "dps": d} for n, c, d in players],
            "loot": []}


def summary(*bosses: dict) -> dict:
    return {"fight_ms": 0, "players": [], "bosses": list(bosses)}


def test_parse_grenzen():
    assert percentile(5, []) is None
    assert percentile(100, [10, 20, 30]) == 100
    assert percentile(1, [10, 20, 30]) == 0
    assert percentile(20, [10, 20, 30, 40]) == 50
    assert percentile(40, [10, 20, 30, 40]) == 100


def test_paare_nur_getoetete_bosse_mit_klasse():
    s = summary(boss(1, [("A", "ranger", 100), ("B", None, 50)]), boss(2, [("A", "ranger", 100)], killed=False))
    assert needed_pairs([s]) == {(1, "ranger")}


def test_gilde_bestwert_je_charakter():
    runs = [summary(boss(1, [("A", "ranger", 100), ("B", "ranger", 200)])),
            summary(boss(1, [("A", "ranger", 300), ("A", "gladiator", 50)]))]
    assert guild_bests(runs) == {(1, "ranger"): [200.0, 300.0], (1, "gladiator"): [50.0]}
