"""Die Daten der Boss-Warnungen: jede Mechanik hat Schalter, Farbe, Boss und englische Texte; die Schalter
der Seite ergeben sich aus den Daten."""
from deckbar_daemon.aion2.gamedata import BOSSES, CALLOUTS, MECHANICS, ZONES
from deckbar_daemon.aion2.rules import COLORS, DUNGEON_GROUPS, ENGLISH, SWITCHES


def test_jede_mechanik_hat_schalter_farbe_und_boss():
    for m in MECHANICS["mechaniken"]:
        assert m["gruppe"] in DUNGEON_GROUPS[m["dungeon"]], m["gruppe"]
        assert m["farbe"] in COLORS
        assert all(BOSSES[npc] == m["dungeon"] for npc in m["bosse"]), m["gruppe"]
        for text in (m["titel"], m["hinweis"], m["meldung"]):  # alles hat eine englische Fassung
            assert text in ENGLISH, f"{m['gruppe']}: {text}"


def test_schalter_kommen_aus_den_daten():
    """Je Gruppe ein Schalter bei ihrem Dungeon; die Lernhilfe nur dort, wo die Daten sie nennen."""
    krao, fire_temple = DUNGEON_GROUPS["Krao Cave"], DUNGEON_GROUPS["Feuertempel"]
    assert krao["berk_stagger"] == "Berk: Jetzt staggern"
    assert "casts" in krao and "casts" not in fire_temple
    assert fire_temple["ansage_kromede_s_desire"] == "Kromedes Gier: Ansagen"
    assert DUNGEON_GROUPS["Citadel of the Fallen Daeva"] == {}
    assert list(SWITCHES["alle"]) == ["groggy", "hp", "gruppe_lp", "flaeche"]
    assert set(ZONES.values()) | set(BOSSES.values()) <= set(DUNGEON_GROUPS)  # jeder Dungeon ist bekannt


def test_ansage_ersetzt_eigene_regel():
    own = {skill for m in MECHANICS["mechaniken"] for skill in m["wann"].get("skills", [m["wann"].get("id")])}
    # Zwei ältere eigene Regeln laufen neben ihrer Ansage weiter (Regen-Vorbote plant die Teufelsflamme,
    # Raurs Konter): Sie standen bis Umbauschritt 7 im Code und fielen hier nicht auf.
    assert own & {call["id"] for call in CALLOUTS["rufe"]} == {1801185, 1504450}
