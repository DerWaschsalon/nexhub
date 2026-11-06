"""Boss-Ansagen wie im A2Tools-Plugin „Boss Callouts“ (taengu/A2Tools-Plugins, GPL-3.0, logic.js),
nach Python übertragen. Die Daten stehen in ansagen.json (werkzeuge/ansagen.py).

Gesagt wird nur, was das Spiel ohnehin zeigt: die Zeile des Bosses, die Zeit seiner Cast-Leiste, ein
Buff auf ihm und wie lange er liegt. Die von Hand geprüften Mechaniken bringen eine kurze Anweisung
mit („Lila — keine Magieangriffe“), einen Countdown, solange der Buff liegt, und danach „Wieder
angreifen“. Bei Vakrons Sprung piept es zu jeder Welle.

Die Pakete kommen von jedem Wesen, auch von Spielern. Welcher Boss ein Wesen ist, merkt sich die Klasse
erst, wenn es einen der Skills dieses Bosses einsetzt (eine halbe Stunde lang). Nur so lässt sich ein
Buff, den jedes Monster bekommen kann (Raserei, Benommenheit), dem richtigen Boss zuordnen.
"""
from __future__ import annotations

from .warnung import GELB, GRUEN, ORANGE, Regel, WarnZentrale
from .zustand import BOSS_ANSAGEN

WIEDERHOLUNG_S = 1.2   # derselbe Auslöser desselben Wesens so kurz danach: nur einmal
OHNE_LEISTE_S = 4.0    # so lange steht eine Ansage ohne Cast-Leiste
SICHER_S = 2.5         # „Wieder angreifen“
WELLEN_ABSTAND_S = 0.4  # mehrere Geschosse einer Welle: ein Piepton
WELLEN_FUER_S = 8.0    # so lange nach dem Skill zählen seine Wellen
BOSS_MERKEN_S = 30 * 60
REIHE_ABSTAND_S = 6.0  # ein Zeichen so lange nach dem letzten beginnt eine neue Reihe
REIHE_ZEIGEN_S = 12.0  # die Reihe bleibt stehen, solange sie abläuft
PHASE_S = (0.5, 120.0)  # Dauer eines Buffs, auf diesen Bereich begrenzt
SCHON_GESAGT_S = 6.0   # Anweisung kam eben schon: zum Beginn der Phase nicht noch einmal sagen
VORSCHAU_PHASE_S = 5.0  # ▶ auf der NexBoard-Seite: die Phase so lange, wie im Plugin
VORSCHAU_NIEMAND = -1   # Wesen der Vorschau


class Ansagen:
    """Hört auf Cast-Leiste, Skill, Wellen und Effekte und gibt die passenden Ansagen an die WarnZentrale."""

    def __init__(self, zentrale: WarnZentrale, daten: dict = BOSS_ANSAGEN) -> None:
        self.zentrale = zentrale
        self.bosse = daten["bosse"]
        self.sicher = daten["sicher"]
        self.rufe: dict[tuple[str, int], list[dict]] = {}  # (Art, ID) -> Rufe (einer je Boss)
        self.phasen_rufe: dict[int, list[dict]] = {}       # Buff-ID -> Rufe mit dieser Phase
        self.koenner: dict[int, set[str]] = {}             # Skill -> Bosse, die ihn einsetzen
        for ruf in daten["rufe"]:
            self.rufe.setdefault((ruf["art"], ruf["id"]), []).append(ruf)
            if "phase" in ruf:
                self.phasen_rufe.setdefault(ruf["phase"]["effekt"], []).append(ruf)
            if ruf["art"] != "effekt":
                self.koenner.setdefault(ruf["id"], set()).add(ruf["boss"])
        for slug, boss in self.bosse.items():
            for skill in boss["skills"]:
                self.koenner.setdefault(skill, set()).add(slug)
        self.effekte = {i for art, i in self.rufe if art == "effekt"} | set(self.phasen_rufe)
        self.wesen: dict[int, tuple[set[str], float]] = {}      # Entity -> (Bosse, zuletzt gesehen)
        self.zuletzt: dict[tuple[int, str, int], float] = {}   # (Entity, Art, ID) -> Zeit
        self.gesagt: dict[int, float] = {}                      # id(Ruf) -> Zeit der letzten Ansage
        self.phasen: dict[tuple[int, int], tuple[dict, float]] = {}  # (Entity, Instanz) -> (Ruf, Ende)
        self.wellen: dict[tuple[int, int], list] = {}           # (Entity, Skill) -> [Ruf, Beginn, letzter Piep]
        self.reihen: dict[tuple[int, str], tuple[list[str], float]] = {}  # (Entity, Reihe) -> (Wörter, zuletzt)
        self.nach_schluessel = {r["schluessel"]: r for r in daten["rufe"]}
        self.vorschau_phasen: list[tuple[float, dict]] = []  # (fällig um, Ruf)

    # ---------- Eingänge (aus dem Mitschnitt-Thread) ----------
    def leiste(self, caster: int, skill: int) -> None:
        self._ausloeser("leiste", caster, skill)

    def skill(self, caster: int, skill: int, _ziel: int | None = None) -> None:
        self._ausloeser("skill", caster, skill)

    def effekt(self, wesen: int, instanz: int, effekt: int, dauer: float) -> None:
        for ruf in self.phasen_rufe.get(effekt, []):
            if self._an(ruf):
                self._phase_beginnt(ruf, wesen, instanz, dauer)
                break
        self._ausloeser("effekt", wesen, effekt)

    def effekt_weg(self, wesen: int, instanz: int) -> None:
        self._phase_endet((wesen, instanz))

    def welle(self, caster: int, skill: int) -> None:
        w = self.wellen.get((caster, skill))
        jetzt = self.zentrale.uhr()
        if not w or jetzt - w[1] > WELLEN_FUER_S or jetzt - w[2] < WELLEN_ABSTAND_S:
            return
        w[2] = jetzt
        if self._an(w[0]) and self.zentrale.k["wellen_ton"]:
            self.zentrale.laut.append(("welle", ""))  # kurzer Piepton

    def testen(self, schluessel: str) -> None:
        """▶ auf der NexBoard-Seite: der Ruf, wie ein Kampf ihn bringt (mit eigenen Worten), danach seine
        Phase auf 5 s gekürzt und „Wieder angreifen“. Gilt auch für einen abgehakten Ruf."""
        ruf = self.nach_schluessel.get(schluessel)
        if not ruf:
            return
        jetzt = self.zentrale.uhr()
        if "reihe" in ruf:
            self._reihe(ruf, VORSCHAU_NIEMAND, jetzt)
        else:
            self._rufen(ruf, VORSCHAU_NIEMAND, jetzt)
        if "phase" in ruf:
            self.vorschau_phasen.append((jetzt + min(ruf.get("vorlauf") or 1.8, 3.0), ruf))

    def takt(self) -> None:
        """Abgelaufene Phasen beenden (der Server schickt das Ende nicht immer), Vorschau-Phasen beginnen."""
        jetzt = self.zentrale.uhr()
        for faellig, ruf in [v for v in self.vorschau_phasen if v[0] <= jetzt]:
            self.vorschau_phasen.remove((faellig, ruf))
            self._phase_beginnt(ruf, VORSCHAU_NIEMAND, VORSCHAU_NIEMAND, VORSCHAU_PHASE_S)
        for schluessel, (_ruf, ende) in list(self.phasen.items()):
            if ende <= jetzt:
                self._phase_endet(schluessel)

    # ---------- Ablauf ----------
    def _ausloeser(self, art: str, wesen: int, i: int) -> None:
        jetzt = self.zentrale.uhr()
        if art != "effekt":
            self._lernen(wesen, i, jetzt)
        rufe = self.rufe.get((art, i))
        ruf = rufe and self._waehlen(rufe, wesen, jetzt)
        if not ruf or not self._an(ruf):
            return
        letzter = self.zuletzt.get((wesen, art, i))
        self.zuletzt[(wesen, art, i)] = jetzt
        if letzter is not None and jetzt - letzter < WIEDERHOLUNG_S:
            return
        if "reihe" in ruf:
            self._reihe(ruf, wesen, jetzt)
        else:
            self._rufen(ruf, wesen, jetzt)

    def _lernen(self, wesen: int, skill: int, jetzt: float) -> None:
        """Setzt ein Wesen einen Skill eines Bosses ein, ist es (vermutlich) dieser Boss."""
        bosse = self.koenner.get(skill)
        if bosse:
            bekannt = self.wesen.get(wesen, (set(), jetzt))[0]
            self.wesen[wesen] = (bekannt | bosse, jetzt)

    def _waehlen(self, rufe: list[dict], wesen: int, jetzt: float) -> dict | None:
        """Von den Rufen eines Auslösers (einer je Boss) der für dieses Wesen. Ist das Wesen unbekannt,
        schweigt ein Ruf, der seinen Boss kennen muss."""
        bosse, gesehen = self.wesen.get(wesen, (set(), -BOSS_MERKEN_S))
        if jetzt - gesehen < BOSS_MERKEN_S:
            for ruf in rufe:
                if ruf["boss"] in bosse:
                    return ruf
        return next((r for r in rufe if not r.get("braucht_boss")), None)

    def _an(self, ruf: dict) -> bool:
        """Boss nicht abgeschaltet (Schalter je Boss), Ruf nicht abgehakt, passender Dungeon."""
        return ruf["schluessel"] not in self.zentrale.k["ruf_aus"] and self.zentrale.gruppe_an(ruf["gruppe"])

    def _rufen(self, ruf: dict, wesen: int, jetzt: float) -> None:
        gross, klein, sagen = self._worte(ruf)
        self.gesagt[id(ruf)] = jetzt
        regel = Regel(gross, klein or self._boss(ruf), ruf.get("vorlauf") or OHNE_LEISTE_S, GELB,
                      ruf["gruppe"], sprechen=sagen)
        self._zeigen(regel, jetzt)
        if ruf.get("wellen"):
            self.wellen[(wesen, ruf["id"])] = [ruf, jetzt, 0.0]

    def _worte(self, ruf: dict) -> tuple[str, str, tuple[str, ...]]:
        """(groß, klein, gesprochen) nach dem eingestellten Stil: beides, nur Anweisung, nur Zeile."""
        eigene = self._eigene(ruf)
        if eigene:
            return eigene, "", (eigene,)  # eigene Worte gelten statt des Rufs, egal welcher Stil
        stil = self.zentrale.k["ansage_stil"]
        zeile, anweisung = self._text(ruf.get("zeile")), self._text(ruf.get("anweisung"))
        buff = self._text(ruf.get("buff")) if ruf["art"] == "effekt" else ""
        if stil == "zeile":
            gross = zeile or anweisung or buff
            return gross, "", (gross,)
        if stil == "anweisung":
            gross = anweisung or zeile or buff
            return gross, "" if anweisung else buff, (gross,)
        if anweisung and zeile:
            return anweisung, zeile, (anweisung, zeile)
        gross = anweisung or zeile or buff
        return gross, buff if buff and zeile else "", (gross,)

    def _reihe(self, ruf: dict, wesen: int, jetzt: float) -> None:
        """Eine Reihenfolge, die der Boss Zeichen für Zeichen zeigt (Talisras Speere: Dunkel, Dunkel,
        Licht): jedes Zeichen gesagt, angezeigt die Reihe bis hierher."""
        schluessel = (wesen, ruf["reihe"])
        woerter, zuletzt = self.reihen.get(schluessel, ([], -REIHE_ABSTAND_S))
        if jetzt - zuletzt >= REIHE_ABSTAND_S:
            woerter = []
        wort = self._eigene(ruf) or self._text(ruf.get("anweisung"))
        woerter = woerter + [wort]
        self.reihen[schluessel] = (woerter, jetzt)
        self._zeigen(Regel(" → ".join(woerter), self._boss(ruf), REIHE_ZEIGEN_S, GELB, ruf["gruppe"],
                           sprechen=(wort,)), jetzt)

    def _phase_beginnt(self, ruf: dict, wesen: int, instanz: int, dauer: float) -> None:
        """Der Buff einer geprüften Mechanik liegt: Countdown über seine echte Dauer."""
        jetzt = self.zentrale.uhr()
        phase = ruf["phase"]
        dauer = min(max(dauer or phase["sekunden"], PHASE_S[0]), PHASE_S[1])
        nur_zeile = self.zentrale.k["ansage_stil"] == "zeile"
        anzeige = (nur_zeile and self._text(phase.get("name"))) or self._text(phase.get("anzeige")) \
            or self._text(ruf.get("anweisung"))
        neu = (wesen, instanz) not in self.phasen
        self.phasen[(wesen, instanz)] = (ruf, jetzt + dauer)
        schon_gesagt = jetzt - self.gesagt.get(id(ruf), -SCHON_GESAGT_S) < SCHON_GESAGT_S
        sagen = (anzeige,) if neu and not schon_gesagt else ()
        klein = "" if nur_zeile else self._text(phase.get("name"))
        self._zeigen(Regel(anzeige, klein, dauer, ORANGE, ruf["gruppe"], sprechen=sagen), jetzt)

    def _phase_endet(self, schluessel: tuple[int, int]) -> None:
        eintrag = self.phasen.pop(schluessel, None)
        if not eintrag:
            return
        ruf = eintrag[0]
        if any(r is ruf for r, _ in self.phasen.values()):
            return  # dieselbe Mechanik läuft noch auf einem anderen: noch nicht sicher
        sicher = self._text(self.sicher)
        self._zeigen(Regel(sicher, self._boss(ruf), SICHER_S, GRUEN, ruf["gruppe"], sprechen=(sicher,)),
                     self.zentrale.uhr())

    # ---------- Hilfen ----------
    def _zeigen(self, regel: Regel, jetzt: float) -> None:
        self.zentrale.zeigen(regel, jetzt)

    def _eigene(self, ruf: dict) -> str:
        """Eigene Worte für diesen Ruf von der NexBoard-Seite, sonst leer."""
        return str(self.zentrale.k["eigene_worte"].get(ruf["schluessel"], "")).strip()

    def _boss(self, ruf: dict) -> str:
        return self._text(self.bosse[ruf["boss"]]["name"])

    def _text(self, texte: dict | None) -> str:
        """Der Text in der eingestellten Sprache (Deutsch oder Englisch)."""
        return texte[self.zentrale.k["sprache"]] if texte else ""


ARTEN_SEITE = {"leiste": "Zauber", "skill": "Fertigkeit", "effekt": "Buff am Boss"}  # Wörter des Plugins


def seitenliste(daten: dict = BOSS_ANSAGEN) -> dict[str, list[dict]]:
    """Die Rufe je Schalter (Boss) für die NexBoard-Seite: Schlüssel, Art und die Vorgabe auf Deutsch.
    Zwei Rufe mit demselben Schlüssel (Vakrons Sprung, normal und leicht) sind eine Zeile."""
    liste: dict[str, list[dict]] = {}
    gesehen: set[str] = set()
    for ruf in daten["rufe"]:
        if ruf["schluessel"] in gesehen:
            continue
        gesehen.add(ruf["schluessel"])
        vorgabe = (ruf.get("anweisung") or ruf.get("zeile") or ruf.get("buff"))["de"]
        liste.setdefault(ruf["gruppe"], []).append(
            {"schluessel": ruf["schluessel"], "art": ARTEN_SEITE[ruf["art"]], "vorgabe": vorgabe,
             "zeile": ruf["zeile"]["de"] if ruf.get("anweisung") and ruf.get("zeile") else ""})
    return liste
