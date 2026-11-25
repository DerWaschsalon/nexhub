"""Boss-Ansagen nach dem A2Tools-Plugin: Bosserkennung, Phasen, Wellen, Reihenfolge, Stil, eigene Worte."""
import pytest
from aion2_bench import ME, Bench

from deckbar_daemon.aion2.callouts import page_list
from deckbar_daemon.aion2.gamedata import CALLOUTS
from deckbar_daemon.aion2.rules import DUNGEON_GROUPS


def text(de: str, en: str = "") -> dict:
    return {"de": de, "en": en or de}


# Kleine Liste im Format von callouts.json (Werte wie im Plugin)
DATA = {
    "sicher": text("Wieder angreifen", "Safe to attack"),
    "bosse": {
        "thamon": {"name": text("Thamon"), "dungeon": "Vakron Sky Island", "skills": [1604600]},
        "vakron": {"name": text("Vakron"), "dungeon": "Vakron Sky Island", "skills": [1604370]},
        "talisra": {"name": text("Talisra"), "dungeon": "Shattered Arkanis", "skills": []},
    },
    "rufe": [
        {"schluessel": "thamon-violet", "art": "leiste", "id": 1604670, "boss": "thamon", "gruppe": "ansage_thamon",
         "vorlauf": 1.79, "zeile": text("Violettes Licht schießt empor!"),
         "anweisung": text("Lila — keine Magieangriffe"),
         "phase": {"effekt": 16046701, "sekunden": 10.0, "anzeige": text("Keine Magie"),
                   "name": text("Mystisches Gebrüll")}},
        {"schluessel": "vakron-jump", "art": "skill", "id": 1604390, "boss": "vakron", "gruppe": "ansage_vakron",
         "zeile": text("Die Wut der Erde …"), "anweisung": text("Springen!"), "wellen": True},
        {"schluessel": "abnormal:10000008:vakron", "art": "effekt", "id": 10000008, "boss": "vakron",
         "gruppe": "ansage_vakron", "zeile": text("Ich werde jene bestrafen …"), "buff": text("Raserei"),
         "braucht_boss": True},
        {"schluessel": "talisra-dark", "art": "skill", "id": 1801730, "boss": "talisra", "gruppe": "ansage_talisra",
         "anweisung": text("Dunkel"), "reihe": "speere"},
        {"schluessel": "talisra-light", "art": "skill", "id": 1801735, "boss": "talisra", "gruppe": "ansage_talisra",
         "anweisung": text("Licht"), "reihe": "speere"},
    ],
}
VIOLET, JUMP, FRENZY, VIOLET_BUFF = 1604670, 1604390, 10000008, 16046701


@pytest.fixture
def bench() -> Bench:
    return Bench(own_id=None, callouts=DATA)


def shown(bench: Bench) -> list[tuple[str, str, float]]:
    return [(w.rule.title, w.rule.hint, round(w.rest(bench.now), 2)) for w in bench.board.snapshot()]


def test_nur_mich_schweigt_bei_fremdem_ziel(bench):
    bench.settings.only_me = True
    bench.world.own_id, bench.world.players[9] = ME, "Andere"
    bench.callouts.bar(70, VIOLET, 9)
    bench.callouts.effect(9, 1, FRENZY, 5.0)
    assert (shown(bench), bench.sounds) == ([], [])
    assert "thamon" in bench.callouts.beings[70][0]  # Boss trotzdem erkannt
    bench.callouts.bar(70, VIOLET, ME)  # auf mich
    assert len(shown(bench)) == 1
    bench.now += 5
    bench.callouts.bar(70, VIOLET, 70)  # auf sich selbst: Fläche, Angriff auf alle
    assert len(shown(bench)) == 1
    bench.settings.only_me = False
    bench.now += 5
    bench.callouts.bar(70, VIOLET, 9)
    assert len(shown(bench)) == 1


def test_leiste_mit_anweisung_und_zeile(bench):
    bench.callouts.bar(70, VIOLET)
    assert shown(bench) == [("Lila — keine Magieangriffe", "Violettes Licht schießt empor!", 1.79)]
    assert bench.sounds == [("ansage", "Lila — keine Magieangriffe"), ("zeile", "Violettes Licht schießt empor!")]


def test_stil_nur_zeile_und_nur_anweisung(bench):
    bench.settings.style = "zeile"
    bench.callouts.bar(70, VIOLET)
    assert bench.sounds == [("ansage", "Violettes Licht schießt empor!")]
    bench.sounds.clear()
    bench.now += 5
    bench.settings.style = "anweisung"
    bench.callouts.bar(70, VIOLET)
    assert bench.sounds == [("ansage", "Lila — keine Magieangriffe")]


def test_phase_mit_echter_dauer_und_wieder_angreifen(bench):
    bench.callouts.bar(70, VIOLET)
    bench.now += 1.8
    bench.sounds.clear()
    bench.callouts.effect(70, 3, VIOLET_BUFF, 8.5)  # Buff liegt 8,5 s (nicht die 10 s aus der Liste)
    assert shown(bench) == [("Keine Magie", "Mystisches Gebrüll", 8.5)]
    assert bench.sounds == []  # Anweisung kam eben schon
    bench.now += 8.5
    bench.callouts.tick()
    assert shown(bench)[0][:2] == ("Wieder angreifen", "Thamon")
    assert bench.sounds == [("ansage", "Wieder angreifen")]


def test_phase_endet_frueher(bench):
    bench.callouts.effect(70, 3, VIOLET_BUFF, 10.0)
    assert bench.sounds == [("ansage", "Keine Magie")]  # ohne Leiste davor: jetzt sagen
    bench.now += 2
    bench.callouts.effect_gone(70, 3)
    assert shown(bench)[0][0] == "Wieder angreifen"


def test_piep_je_welle(bench):
    bench.callouts.skill(80, JUMP)
    bench.sounds.clear()
    for after in (1.7, 1.8, 3.4, 5.1, 9.5):  # 1,8 = zweites Geschoss derselben Welle, 9,5 zu spät
        bench.now = 100 + after
        bench.callouts.wave(80, JUMP)
    assert bench.sounds == [("welle", "")] * 3
    bench.settings.wave_sound = False
    bench.now += 0.5
    bench.callouts.skill(80, JUMP)
    bench.now += 1.7
    bench.sounds.clear()
    bench.callouts.wave(80, JUMP)
    assert bench.sounds == []


def test_raserei_nur_bei_erkanntem_boss(bench):
    bench.callouts.effect(80, 1, FRENZY, 30)  # Wesen unbekannt: jedes Monster kann Raserei bekommen
    assert shown(bench) == []
    bench.callouts.skill(80, 1604370)  # eigener Skill von Vakron: jetzt ist das Wesen bekannt
    bench.now += 5
    bench.callouts.effect(80, 2, FRENZY, 30)
    assert shown(bench) == [("Ich werde jene bestrafen …", "Raserei", 4.0)]


def test_reihenfolge_der_speere(bench):
    for skill in (1801730, 1801730, 1801735):
        bench.callouts.skill(90, skill)
        bench.now += 2
    assert shown(bench)[0][0] == "Dunkel → Dunkel → Licht"
    bench.now += 7
    bench.callouts.skill(90, 1801735)  # lange danach: neue Reihe
    assert shown(bench)[0][0] == "Licht"


def test_doppelter_ausloeser_einmal(bench):
    bench.callouts.bar(70, VIOLET)
    bench.now += 0.5
    bench.callouts.bar(70, VIOLET)
    assert len(bench.sounds) == 2  # Anweisung und Zeile, nicht doppelt


def test_abgeschalteter_boss_und_anderer_dungeon(bench):
    bench.settings.off = ["ansage_thamon"]
    bench.callouts.bar(70, VIOLET)
    assert shown(bench) == []
    bench.settings.off = []
    bench.world.dungeon = "Draupnir"
    bench.callouts.bar(70, VIOLET)
    assert shown(bench) == []


def test_eigene_worte_statt_des_rufs(bench):
    bench.settings.own_words = {"thamon-violet": "Lila, Magie stopp"}
    bench.callouts.bar(70, VIOLET)
    assert shown(bench) == [("Lila, Magie stopp", "Thamon", 1.79)]
    assert bench.sounds == [("ansage", "Lila, Magie stopp")]


def test_abgehakter_ruf_ganz_aus_aber_vorschau_geht(bench):
    bench.settings.calls_off = ["thamon-violet"]
    bench.callouts.bar(70, VIOLET)
    bench.callouts.effect(70, 3, VIOLET_BUFF, 10)  # auch sein Countdown
    assert shown(bench) == []
    bench.callouts.test("thamon-violet")  # ▶ gilt auch für einen abgehakten Ruf
    assert shown(bench)[0][0] == "Lila — keine Magieangriffe"
    bench.now += 1.79
    bench.callouts.tick()
    assert shown(bench) == [("Keine Magie", "Mystisches Gebrüll", 5.0)]
    bench.now += 5
    bench.callouts.tick()
    assert shown(bench)[0][0] == "Wieder angreifen"


def test_signale_des_kampfes_kommen_an(bench):
    """Verdrahtung: Cast-Leiste aus dem Paket bis zur Ansage."""
    bench.fight.cast_bar.emit(70, VIOLET, None)
    assert shown(bench)[0][0] == "Lila — keine Magieangriffe"
    assert VIOLET_BUFF in bench.fight.effect_ids


# ---------------------------------------------------------------- die echten Daten
def test_jeder_ruf_hat_boss_schalter_und_text():
    for call in CALLOUTS["rufe"]:
        boss = CALLOUTS["bosse"][call["boss"]]
        assert call["gruppe"] in DUNGEON_GROUPS[boss["dungeon"]], call
        assert call.get("zeile") or call.get("anweisung") or call.get("buff"), call


def test_liste_fuer_die_seite():
    listing = page_list()
    assert sum(len(calls) for calls in listing.values()) == len({c["schluessel"] for c in CALLOUTS["rufe"]})
    assert {"schluessel": "vakron-jump", "art": "Fertigkeit", "vorgabe": "Springen!",
            "zeile": "Die Wut der Erde wird alle Hochmütigen strafen, die es wagen, ihren Fuß auf diesen Boden zu "
                     "setzen!"} in listing["ansage_vakron"]
