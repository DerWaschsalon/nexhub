"""Boss-Warnungen: Auslöser aus mechanics.json (Cast, Status, Treffer, Stagger), Kampfhilfen, Lernhilfe,
Vorhersagen und Zeitfenster. Die Skills sind die aus dem Spiel."""
import pytest
from aion2_bench import ME, Bench

MARK_OF_DEATH, RAIN, AREA_PHASE = 1801070, 1801110, 1801186  # Kromedes Skills (Feuertempel)
RAUR, THAMON, BERK = 2300206, 2300811, 2300171  # Boss-NPCs
ANNA = 9


@pytest.fixture
def bench() -> Bench:
    b = Bench(sounds={"schwert": "aus"})
    b.world.players.update({ME: "Ich", ANNA: "Anna"})
    b.world.bosses.update({70: RAUR, 71: THAMON, 72: BERK})
    return b


# ---------------------------------------------------------------- Feuertempel: Vorhersagen und Ketten
def test_regen_kuendigt_flamme_an_und_todesmal_ersetzt_sie(bench):
    bench.cast(1, RAIN, 1)
    assert bench.titles() == ["Regen des Hasses", "Teufelsflamme erwartet"]
    bench.now += 3.65
    bench.cast(1, MARK_OF_DEATH, ANNA)
    flame = [w for w in bench.board.snapshot() if w.rule.group == "flamme"]
    assert [w.rule.title for w in flame] == ["Todesmal"]
    assert bench.now - flame[0].since == pytest.approx(3.65)  # die Kette läuft seit dem Regen
    assert not flame[0].me


def test_abgeschaltete_meldung_kommt_nicht(bench):
    bench.settings.off = ["flamme"]
    bench.cast(1, RAIN, 1)
    assert bench.titles() == ["Regen des Hasses"]


def test_warnung_aus_anderem_dungeon_kommt_nicht(bench):
    bench.world.dungeon = "Ferocious Horn Den"
    bench.cast(1, RAIN, 1)
    assert bench.titles() == []
    bench.world.dungeon = "Feuertempel"
    bench.cast(1, 1504450, 1)  # Raurs Konter gehört nach Urugugu
    assert bench.titles() == []


def test_flaechenphase_plant_regen_und_flamme(bench):
    bench.cast(1, AREA_PHASE, 1)
    assert [round(rest) for _, rest in bench.board.preview()] == [22, 30]
    bench.now += 12.3
    assert bench.titles() == ["Regen des Hasses kommt", "Teufelsflamme erwartet"]


def test_regen_zeitfenster(bench):
    bench.cast(1, RAIN, 1)
    bench.now += 10
    assert bench.board.preview()[0][0] == "Regen des Hasses frühestens"
    bench.now += 40
    assert bench.board.preview() == [("Regen des Hasses jederzeit möglich", 0.0)]


def test_klon_phase_und_heulende_flamme(bench):
    bench.cast(1, 1801109, 1)
    bench.cast(1, 1801130, 1)
    assert bench.titles() == ["Heulende Flamme", "Klon-Phase"]


def test_schwert_ohne_ton(bench):
    bench.cast(1, 1801050, 1)
    assert (bench.titles(), bench.sounds) == (["Schwert"], [])
    bench.cast(1, 1600720, 1)
    assert bench.sounds == [("ansage", "Gigantisches Beben")]


# ---------------------------------------------------------------- wen es trifft
def test_todesmal_auf_mir_und_auf_anderen(bench):
    bench.cast(1, MARK_OF_DEATH, ANNA)
    assert bench.board.snapshot()[0].title() == "Todesmal auf Anna"
    assert bench.sounds[0] == ("ansage", "Todesmal auf Anna")
    bench.now += 10
    bench.cast(1, MARK_OF_DEATH, ME)
    assert bench.board.snapshot()[0].me


def test_nur_mich_schweigt_bei_anderen(bench):
    bench.settings.only_me = True
    bench.cast(1, MARK_OF_DEATH, ANNA)
    bench.party.hp.emit(ANNA, 0.1)
    assert (bench.titles(), bench.sounds) == ([], [])
    bench.cast(1, MARK_OF_DEATH, ME)
    assert bench.board.snapshot()[0].title() == "Todesmal  –  DU!"


def test_status_nur_auf_mir(bench):
    bench.status(ANNA, 16008401)  # Ignus' Bombe auf einem anderen: nichts
    assert bench.titles() == []
    bench.status(ME, 16008401)
    assert bench.sounds == [("ansage", "Verzögerte Explosion auf dir")]


def test_zikel_blutung_nur_auf_mir_und_linie_nur_im_albtraum(bench):
    bench.status(ANNA, 12000151)
    assert bench.titles() == []
    bench.status(ME, 12000151)
    assert bench.sounds == [("ansage", "Blutung auf dir")]
    bench.world.dungeon = "Feuertempel"
    bench.cast(1, 1802380, 1)
    assert bench.titles() == ["Blutung"]
    bench.world.dungeon = "Albtraum"
    bench.cast(1, 1802380, 1)
    bench.now += 5
    bench.cast(1, 1802381, 1)  # zweite Linie ersetzt die erste
    assert bench.titles() == ["Zweite Linie"]
    bench.cast(1, 1802445, ME)  # Ziel bin ich: ohne eigenen Namen
    assert bench.sounds[-1] == ("ansage", "Blutschlag")


def test_zikel_graue_schlaege_ohne_ton(bench):
    bench.world.dungeon = "Albtraum"
    bench.settings.sounds = {"zikel_angriffe": "aus"}
    bench.cast(1, 1802435, ME)
    assert (bench.titles(), bench.sounds) == (["Schlag"], [])


def test_effekt_auf_dem_boss_und_danach(bench):
    bench.status(ANNA, 15044501)  # Konter auf einem Spieler zählt nicht
    assert bench.shown() == []
    bench.status(70, 15044501)
    assert bench.shown() == [("Konter-Haltung", "Nicht angreifen, zurückgehen")]
    bench.now += 4.9  # nach dem Einschlag: Folge-Hinweis derselben Gruppe
    assert bench.shown() == [("Konter-Haltung", "Abstand halten")]


def test_effekt_auf_mitspieler_nennt_ihn(bench):
    bench.status(ME, 16047201)  # auf mir: diese Regel gilt nur für Mitspieler
    assert bench.shown() == []
    bench.status(ANNA, 16047201)
    assert bench.shown() == [("Versteinert auf Anna", "Befreien")]


def test_effekt_auf_jedem_spieler(bench):
    bench.status(ANNA, 16056701)  # Nazmun-Bombe beim anderen: Abstand halten
    assert bench.shown() == [("Bombe auf Anna", "Abstand halten")]
    bench.now += 10
    bench.status(ME, 16056701)  # bei mir: weg von der Gruppe
    assert bench.shown() == [("Bombe  –  DU!", "Weg von der Gruppe!")]
    bench.now += 20
    bench.status(ME, 16010302)  # Auldor: auch bei mir zusammenstellen
    assert bench.shown() == [("Sturmstreich  –  DU!", "Zusammenstellen")]


def test_urugugu_sturzschlag_auf_mir_und_wirbel_phase(bench):
    bench.world.dungeon = "Urugugu Canyon"
    bench.cast(1, 1600960, ME)
    assert bench.board.snapshot()[0].title() == "Sturzschlag  –  DU!"
    bench.cast(1, 1601010, 1)  # Sprung in die Mitte: Wirbel-Phase
    bench.now += 8.6
    assert "Wirbel-Phase" in bench.titles()
    bench.status(ME, 15044311)  # Raurs Zeitbombe auf mir
    assert "Zeitbombe" in bench.titles()


# ---------------------------------------------------------------- Treffer, Stagger, Kampfhilfen
def test_treffer_und_cast(bench):
    bench.fight.hit.emit(1605144)
    bench.cast(1, 1604532, None)
    assert bench.titles() == ["Giftpfütze", "Rotation"]


def test_pfuetze_meldet_nicht_im_sekundentakt(bench):
    for _ in range(5):
        bench.fight.hit.emit(1605144)
        bench.now += 0.3
    assert len(bench.sounds) == 1
    bench.now += 2
    bench.fight.hit.emit(1605144)  # Warnung abgelaufen, immer noch drin: wieder melden
    assert len(bench.sounds) == 2


def test_staggern_endet_mit_groggy(bench):
    bench.stagger.ready.emit(70)  # Raur hat keine Stagger-Prüfung
    assert bench.shown() == []
    bench.stagger.ready.emit(72)
    assert bench.shown() == [("Jetzt staggern", "Leiste brechen")]
    bench.stagger.broken.emit(72)
    assert bench.titles() == ["Boss groggy"]


def test_wenig_hp_einmal_und_nur_im_dungeon(bench):
    for hp in (20000, 9000):
        bench.world.own_hp.emit(hp)
    assert bench.titles() == []  # kein Dungeon
    bench.world.dungeon = "Albtraum"
    for hp in (20000, 9000, 8000, 11000, 9000):  # 11000 liegt unter 65 %: keine neue Warnung beim nächsten Fall
        bench.world.own_hp.emit(hp)
    assert bench.sounds == [("ansage", "Heilen!")]


def test_wenig_lp_einmal_bis_zur_erholung(bench):
    bench.party.hp.emit(ANNA, 0.2)
    bench.party.hp.emit(ANNA, 0.1)
    assert bench.shown() == [("Wenig LP auf Anna", "Unter 25 %")]
    assert len(bench.sounds) == 1
    bench.party.hp.emit(ANNA, 0.8)
    bench.now += 10
    bench.party.hp.emit(ANNA, 0.2)
    assert len(bench.sounds) == 2


def test_berserker_in_der_vorschau(bench):
    bench.aids.berserk[72] = bench.now + 90
    assert bench.board.preview() == [("Berserker", 90.0)]


def test_flaeche_unter_mir(bench):
    bench.world.position = (1000.0, 2000.0, 0.0)
    bench.fight.area.emit(1226350, 1900.0, 2000.0, 2.85)  # 9 m daneben: nichts
    assert bench.board.snapshot() == []
    bench.fight.area.emit(1226350, 1300.0, 2000.0, 2.85)  # 3 m: Warnung mit Countdown
    shown = [(w.title(), w.me, w.rule.lead) for w in bench.board.snapshot()]
    assert shown == [("Fläche unter dir  –  DU!", True, 2.85)]
    for _ in range(5):  # weitere Markierungen derselben Welle: keine neue Ansage
        bench.fight.area.emit(1226350, 1000.0, 2000.0, 2.85)
    assert len(bench.sounds) == 1
    bench.world.position = None
    bench.now += 10
    bench.fight.area.emit(1226350, 1000.0, 2000.0, 2.85)  # ohne Position: nichts
    assert bench.board.snapshot() == []


# ---------------------------------------------------------------- Lernhilfe
def test_lernhilfe_pro_boss(bench):
    bench.world.dungeon = "Ferocious Horn Den"
    bench.world.bosses.update({80: 2300908, 81: 2300910})  # Kwapo mit Cast-Warnung, Nuakum noch ohne
    bench.cast(81, 1910261, 1)  # Nuakum: grau zeigen, damit man ihn auswerten kann
    bench.cast(8, 1910261, 1)  # kein Boss: nichts
    assert bench.groups() == ["casts"]
    bench.now += 10
    bench.cast(80, 1606999, 1)  # unbekannter Cast von Kwapo: keine Lernhilfe mehr
    assert bench.groups() == []
    bench.cast(80, 1606910, 1)  # bekannte Mechanik
    assert [w.title() for w in bench.board.snapshot()] == ["Donnergrollen"]


def test_todesursache_nimmt_die_letzte_warnung_ohne_lernhilfe(bench):
    bench.cast(1, MARK_OF_DEATH, ME)
    assert bench.board.latest(bench.now).rule.title == "Todesmal"
    bench.now += 20
    assert bench.board.latest(bench.now) is None
