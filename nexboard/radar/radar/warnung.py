"""Boss-Warnungen: reagiert auf den Cast-Beginn (0x3802), Status-Effekte (0x382A), Treffer (0x3804)
und die Stagger-Leiste (0xE005).

Feuertempel: alle Zeiten aus der Auswertung von rund 20 Kaempfen (2026-10-23), Skill-Namen aus den
A2Tools-Daten, Ausweich-Hinweise aus dem Guide "Fire Temple Guide Aion 2 Global" (NoBS Game Guides).
Die uebrigen Dungeons kommen aus mechaniken.json (IDs nach glass-cannon, MIT).
"""
from __future__ import annotations

import hashlib
import json
import math
import subprocess
import threading
import time
import wave
from dataclasses import dataclass
from pathlib import Path

from .daten import a2_namen, npc_name
from .konfig import abspielen, konfig_laden
from .zustand import MECHANIKEN

ALARM = Path.home() / ".cache" / "aion2-radar" / "alarm.wav"
ANSAGEN = Path.home() / ".cache" / "aion2-radar" / "ansagen"   # fertig gesprochene Saetze
PIPER = Path.home() / ".local" / "share" / "aion2-radar" / "piper"  # Programm + Stimmen
STIMMEN = {"de": "de_DE-thorsten-medium", "en": "en_US-amy-medium"}

# Skills des Bosses
TODESMAL = 1801070     # markiert einen Spieler, 4,1 s spaeter Teufelsflamme
REGEN = 1801110        # Regen des Hasses: landet unter einem Spieler, 2 s Schaden
REGEN_VORBOTE = 1801185  # in 12 von 15 Faellen 3,8 s vor dem Regen
FLAECHEN = 1801186     # Flaechenphase, Regen in 12 von 15 Faellen 22,25 s spaeter
KLONE = 1801109        # Klon-Phase: Klon-Treffer nach 1,45 s (Linie) und 2,35 s (von hinten)
HEULENDE_FLAMME = 1801130  # zweistufige Flaeche um den Boss, Treffer bis 5 s

REGEN_PAUSE = 42.6     # Regen kam nie frueher als 42,6 s nach dem letzten
REGEN_FENSTER = 30.0   # so lange danach "jederzeit moeglich" zeigen


@dataclass(frozen=True)
class Regel:
    titel: str
    hinweis: str
    vorlauf: float                   # Sekunden bis zum Einschlag
    farbe: tuple[int, int, int]
    gruppe: str                      # neue Warnung ersetzt aeltere derselben Gruppe
    danach: tuple["Regel", ...] = ()  # gleichzeitig ausgeloeste Vorhersagen
    plan: tuple[tuple[float, "Regel"], ...] = ()  # (Sekunden spaeter, Regel)
    auf: str = "du"                  # Status-Effekt zaehlt auf: du, mitspieler, spieler, boss
    hinweis_ich: str = "Weg von der Gruppe!"  # Hinweis, wenn es dich trifft


GRUEN = (0, 230, 118)
LILA, ORANGE, GELB, BLAU, ROT, GRAU = ((186, 85, 255), (255, 120, 0), (255, 210, 0),
                                      (80, 170, 255), (255, 70, 70), (160, 170, 190))


def flamme(vorlauf: float) -> Regel:
    """Vorhersage der Teufelsflamme, bevor das Todesmal kommt."""
    return Regel("Teufelsflamme erwartet", "Todesmal folgt, schon mal verteilen", vorlauf,
                 LILA, "flamme")


REGEN_KOMMT = Regel("Regen des Hasses kommt", "Landet unter dir: erst ausweichen, dann weglaufen",
                    10.0, ORANGE, "regen")

REGELN: dict[int, Regel] = {
    TODESMAL: Regel("Todesmal", "Weg vom Markierten, raus aus der Front", 4.1, LILA, "flamme"),
    REGEN: Regel("Regen des Hasses", "Erst ausweichen, dann weglaufen!", 2.0, ORANGE, "regen",
                 danach=(flamme(7.75),)),
    REGEN_VORBOTE: Regel("Regen des Hasses kommt", "Landet unter dir: erst ausweichen, dann weglaufen",
                         3.8, ORANGE, "regen", danach=(flamme(11.55),)),
    KLONE: Regel("Klon-Phase", "Erst seitlich ausweichen, dann kleiner Sprung zurück", 2.35, BLAU,
                 "klone"),
    HEULENDE_FLAMME: Regel("Heulende Flamme", "Zwei Treffer! Nach dem ersten nicht zurücklaufen",
                           5.0, ROT, "heulen"),
    FLAECHEN: Regel("Flächenphase", "Bodenflächen kommen in Wellen", 3.65, GELB, "flaechen",
                    plan=((12.25, REGEN_KOMMT), (12.25, flamme(17.75)))),
    # Kromede springt auf einen weit entfernten Spieler (Treffer nach 1,25 s)
    1801160: Regel("Sprung", "Springt auf einen entfernten Spieler, ausweichen", 1.25, ROT, "sprung"),
    # Rotflamme Ignus: Donut in drei Wellen (0,15 / 0,65 / 1,15 s)
    1600830: Regel("Flammeneruption", "Ganz nah an den Boss oder ganz weit weg", 1.2, ROT, "ignus"),
    # Schwarzrauch Murute: drei Treffer bei 0,25 / 2,15 / 3,9 s
    1600720: Regel("Gigantisches Beben", "Drei Treffer, alle 2 s ausweichen", 3.9, ROT, "murute"),
}

# Kromedes Schwertangriffe: sie zielt in Blickrichtung, also hinter sie gehen.
# Sehr haeufig und mit 0,2-1,1 s Vorlauf, deshalb standardmaessig ohne Ton.
SCHWERT = Regel("Schwert", "Hinter sie gehen", 1.0, GRAU, "schwert")
for _skill in (1801030, 1801040, 1801050, 1801060, 1801080, 1801090):
    REGELN[_skill] = SCHWERT

# Status-Effekte (0x382A) auf dem eigenen Charakter. Gefunden 2026-10-24: 0,1 s nach Ignus'
# Flammenbombe (1600840) bekommen zwei Spieler 16008401 fuer 3 s, danach entsteht die Feuerpfuetze.
STATUS_REGELN: dict[int, Regel] = {
    16008401: Regel("Verzögerte Explosion", "Pfütze kommt unter dir", 3.0, GRUEN, "bombe"),
}
# Stagger-Leiste eines Bosses gebrochen (0xE005), danach etwa 5 s groggy
GROGGY = Regel("Boss groggy", "Jetzt voller Schaden", 5.0, GELB, "groggy")
# Gruppenmitglied unter 25 % LP; erst wieder melden, wenn es ueber 50 % war
GRUPPE_LP = Regel("Wenig LP", "Unter 25 %", 3.0, ROT, "gruppe_lp")
LP_KNAPP, LP_WIEDER = 0.25, 0.5
# Boden-Markierung (0x3848) mit Mittelpunkt hoechstens so nah an dir (Einstellung flaeche_m)
FLAECHE_DU = "Ausweichen!"
TREFFER_REGELN: dict[int, Regel] = {}  # Skill, der dich trifft (Pfuetzen, Zonen) -> Regel
STAGGER_REGELN: dict[int, Regel] = {}  # Boss-NPC mit Stagger-Pruefung -> „Jetzt staggern“
FARBEN = {"GRUEN": GRUEN, "LILA": LILA, "ORANGE": ORANGE, "GELB": GELB, "BLAU": BLAU, "ROT": ROT}


def mechanik_regel(m: dict) -> Regel:
    """Eine Regel aus mechaniken.json. „danach“ wird als geplante Folge-Warnung derselben Gruppe
    eingehaengt und ersetzt die erste, wenn sie abgelaufen ist."""
    farbe = FARBEN[m["farbe"]]
    plan = ()
    if m.get("danach"):
        folge = Regel(m["titel"], m["danach"]["hinweis"], m["danach"]["sekunden"], farbe, m["gruppe"])
        plan = ((m["sekunden"], folge),)
    return Regel(m["titel"], m["hinweis"], m["sekunden"], farbe, m["gruppe"], plan=plan,
                 auf=m["wann"].get("auf", "du"), hinweis_ich=m.get("hinweis_ich", "Weg von der Gruppe!"))


for _m in MECHANIKEN:
    _regel, _wann = mechanik_regel(_m), _m["wann"]
    if _wann["art"] == "cast":
        REGELN.update({skill: _regel for skill in _wann["skills"]})
    elif _wann["art"] == "effekt":
        STATUS_REGELN[_wann["id"]] = _regel
    elif _wann["art"] == "treffer":
        TREFFER_REGELN.update({skill: _regel for skill in _wann["skills"]})
    elif _wann["art"] == "stagger":
        STAGGER_REGELN.update({npc: _regel for npc in _m["bosse"]})

# Meldungen je Dungeon: Dungeon -> {Gruppe: Name}, steht in meldungen.json (liest auch die
# NexBoard-Seite). Ohne Eintraege = noch keine Warnungen ("fehlt").
_MELDUNGEN = json.loads((Path(__file__).parent / "meldungen.json").read_text())
ALLE_DUNGEONS: dict[str, str] = _MELDUNGEN["alle"]  # gelten in jedem Dungeon
DUNGEONS: dict[str, dict[str, str]] = _MELDUNGEN["dungeons"]

# Englische Texte (Deutsch ist der Grundtext). Fehlt ein Eintrag, bleibt der deutsche Text.
ENGLISCH = {
    " auf ": " on ", " auf dir": " on you",
    # Feldbosse, Termine und Vertraute (Ansagen und die Tabellen auf der NexBoard-Seite)
    "Feldboss": "Field boss", " in 5 Minuten": " in 5 minutes", " ist da": " is up", "lebt": "alive",
    "in": "in", "vermutlich da": "probably up", "unbekannt": "unknown", "Spezial": "Special",
    "Riss": "Rift", " ist offen": " is open", "offen bis": "open until", "Shugo-Fest": "Shugo Festival",
    "Beritra-Luftangriff": "Beritra Air Raid", "Wächterin Kaira": "Watcher Kaira",
    "Tages-Reset": "Daily reset", "Wochen-Reset": "Weekly reset",
    "Kromede: Todesmal / Teufelsflamme": "Kromede: Mark of Death / Demon Flame",
    "Ignus: Verzögerte Explosion (auf dir)": "Ignus: Delayed Explosion (on you)",
    "Boss groggy (alle Dungeons)": "Boss groggy (all dungeons)", "Verzögerte Explosion": "Delayed Explosion",
    "Pfütze kommt unter dir": "Puddle spawns under you",
    "Jetzt voller Schaden": "Full damage now",
    "Kromede: Regen des Hasses": "Kromede: Rain of Hatred",
    "Kromede: Klon-Phase": "Kromede: Clone Phase",
    "Kromede: Heulende Flamme": "Kromede: Howling Flame",
    "Kromede: Flächenphase": "Kromede: AoE Phase",
    "Kromede: Sprung": "Kromede: Dash",
    "Kromede: Schwertangriffe": "Kromede: Sword Attacks",
    "Ignus: Flammeneruption": "Ignus: Flame Eruption",
    "Murute: Gigantisches Beben": "Murute: Great Earthquake",
    # Warnungen
    "Teufelsflamme erwartet": "Demon Flame expected", "Teufelsflamme": "Demon Flame",
    "Todesmal": "Mark of Death", "Regen des Hasses": "Rain of Hatred",
    "Regen des Hasses kommt": "Rain of Hatred incoming",
    "Regen des Hasses frühestens": "Rain of Hatred earliest",
    "Regen des Hasses jederzeit möglich": "Rain of Hatred possible any time",
    "Klon-Phase": "Clone Phase", "Heulende Flamme": "Howling Flame", "Flächenphase": "AoE Phase",
    "Sprung": "Dash", "Flammeneruption": "Flame Eruption", "Gigantisches Beben": "Great Earthquake",
    "Schwert": "Sword",
    "Todesmal folgt, schon mal verteilen": "Mark of Death next, spread out now",
    "Landet unter dir: erst ausweichen, dann weglaufen": "Lands under you: dodge first, then run",
    "Weg vom Markierten, raus aus der Front": "Away from the marked player, out of the front",
    "Erst ausweichen, dann weglaufen!": "Dodge first, then run!",
    "Erst seitlich ausweichen, dann kleiner Sprung zurück": "Dodge sideways, then a small jump back",
    "Zwei Treffer! Nach dem ersten nicht zurücklaufen": "Two hits! Don't walk back after the first",
    "Bodenflächen kommen in Wellen": "Ground AoEs come in waves",
    "Springt auf einen entfernten Spieler, ausweichen": "Leaps at a distant player, dodge",
    "Ganz nah an den Boss oder ganz weit weg": "Hug the boss or go far away",
    "Drei Treffer, alle 2 s ausweichen": "Three hits, dodge every 2 s",
    "Hinter sie gehen": "Get behind her",
    "  –  DU!": "  –  YOU!", "Weg von der Gruppe!": "Away from the group!", "JETZT": "NOW",
    "Wenig LP": "Low HP", "Unter 25 %": "Below 25 %", "Berserker": "Berserk",
    "Fläche unter dir": "AoE under you", "Ausweichen!": "Dodge!",
    "Bodenfläche bei dir (alle Dungeons)": "Ground AoE at you (all dungeons)",
    "Mitspieler mit wenig LP (alle Dungeons)": "Party member with low HP (all dungeons)",
}
for _m in MECHANIKEN:  # englische Texte der Mechaniken stehen in mechaniken.json
    ENGLISCH.update(_m["en"])
# Lernhilfe (jeden Boss-Cast grau zeigen) gilt in Dungeons, fuer die es noch keine Cast-Warnungen gibt
CAST_GRUPPEN = {r.gruppe for r in REGELN.values()}


def tr(text: str) -> str:
    """Text in der eingestellten Sprache."""
    return ENGLISCH.get(text, text) if konfig_laden()["sprache"] == "en" else text


@dataclass
class Warnung:
    regel: Regel
    start: float
    ich: bool = False   # eigener Charakter ist das Ziel (Todesmal)
    seit: float = 0.0   # Beginn der Warnkette, fuer die Auswertung
    ziel: str = ""      # Name des Ziels, falls ein anderer Spieler

    def titel(self) -> str:
        if self.ich:
            return tr(self.regel.titel) + tr("  –  DU!")
        return tr(self.regel.titel) + (tr(" auf ") + self.ziel if self.ziel else "")

    def rest(self, jetzt: float) -> float:
        return self.regel.vorlauf - (jetzt - self.start)


class WarnZentrale:
    """Nimmt Casts aus dem Mitschnitt-Thread an und haelt die aktiven Warnungen."""

    def __init__(self, zustand, uhr=time.time) -> None:
        self.zustand = zustand
        self.uhr = uhr
        self.lock = threading.Lock()
        self.aktiv: list[Warnung] = []
        self.geplant: list[tuple[float, Regel]] = []  # (faellig um, Regel)
        self.regen_zuletzt: float | None = None
        self.laut: list[tuple[str, str]] = []  # (art, text): Piepton oder Ansage, spielt der RadarDienst ab
        self.k = konfig_laden()
        self.an = self.k["warn_an"]
        self._knapp: set[int] = set()  # Mitspieler, die schon als „wenig LP“ gemeldet sind

    def cast(self, caster: int, skill: int, ziel: int | None) -> None:
        regel = REGELN.get(skill)
        dungeon = self.zustand.dungeon
        if not regel and dungeon and not CAST_GRUPPEN & set(DUNGEONS[dungeon]) and caster in self.zustand.bosse:
            regel = cast_regel(skill, self.zustand.bosse[caster])  # Lernhilfe: jeden Boss-Cast zeigen
        if not regel or not self.an:
            return
        if dungeon and regel.gruppe not in {*DUNGEONS[dungeon], "casts"}:
            return  # Skill-ID aus einem anderen Dungeon
        jetzt = self.uhr()
        if skill == REGEN:
            self.regen_zuletzt = jetzt
        ich = skill == TODESMAL and ziel is not None and ziel == self.zustand.eigene_eid
        name = "" if ich else self.zustand.spieler.get(ziel, "")
        with self.lock:
            self._ausloesen(regel, jetzt, ich, name)

    def _ausloesen(self, regel: Regel, jetzt: float, ich: bool = False, name: str = "") -> None:
        """Warnung zeigen, ihre gleichzeitigen Vorhersagen dazu und die geplanten Folgen einreihen.
        Ein neuer Ausloeser ersetzt geplante Vorhersagen derselben Gruppen. Aufruf unter self.lock."""
        gruppen = {r.gruppe for r in (regel, *regel.danach)}
        self.geplant = [(t, r) for t, r in self.geplant if r.gruppe not in gruppen]
        self.geplant += [(jetzt + nach, r) for nach, r in regel.plan]
        self._hinzufuegen(regel, jetzt, ich, name)
        for r in regel.danach:
            self._hinzufuegen(r, jetzt)

    def status(self, ziel: int, sid: int) -> None:
        """Status-Effekt auf dir, einem Mitspieler, irgendeinem Spieler oder dem Boss (Regel.auf)."""
        regel = STATUS_REGELN[sid]
        ich = ziel == self.zustand.eigene_eid
        spieler = ziel in self.zustand.spieler and not ich
        passt = {"du": ich, "mitspieler": spieler, "spieler": ich or spieler,
                 "boss": ziel in self.zustand.bosse}[regel.auf]
        if self.an and passt:
            name = self.zustand.spieler.get(ziel, "") if spieler else ""
            with self.lock:
                self._ausloesen(regel, self.uhr(), ich and regel.auf != "boss", name)

    def treffer(self, skill: int) -> None:
        """Ein Skill vom Boden trifft dich (Pfuetze, Zone): raus da. Pfuetzen treffen mehrmals pro
        Sekunde; solange die Warnung laeuft, zaehlt das als derselbe Treffer (keine Ansage im Sekundentakt)."""
        regel, jetzt = TREFFER_REGELN[skill], self.uhr()
        if not self.an:
            return
        with self.lock:
            if not any(w.regel == regel and w.rest(jetzt) > 0 for w in self.aktiv):
                self._ausloesen(regel, jetzt)

    def staggern(self, boss: int) -> None:
        """Die Stagger-Leiste eines Bosses mit Stagger-Pruefung ist brechbar geworden."""
        regel = STAGGER_REGELN.get(self.zustand.bosse.get(boss, 0))
        if self.an and regel:
            with self.lock:
                self._ausloesen(regel, self.uhr())

    def groggy(self, boss: int) -> None:
        if self.an:
            with self.lock:
                # gebrochen: „Jetzt staggern“ ist erledigt
                self.aktiv = [w for w in self.aktiv if w.regel not in STAGGER_REGELN.values()]
                self._hinzufuegen(GROGGY, self.uhr())

    def flaeche(self, skill: int, x: float, y: float, bis: float) -> None:
        """Ein Monster markiert eine Flaeche am Boden. Liegt ihr Mittelpunkt nah an dir, warnen, mit
        Countdown bis zum Einschlag. Groesse und Form sind unbekannt, deshalb ein fester Abstand."""
        pos = self.zustand.position
        if not self.an or pos is None or bis <= 0:
            return
        if math.hypot(x - pos[0], y - pos[1]) > self.k.get("flaeche_m", 6.0) * 100:  # Welt in cm
            return
        regel = Regel("Fläche unter dir", FLAECHE_DU, bis, ROT, "flaeche", hinweis_ich=FLAECHE_DU)
        jetzt = self.uhr()
        with self.lock:
            # mehrere Markierungen auf einmal (Nazmun: sechs) = eine Warnung, bis sie eingeschlagen ist
            if not any(w.regel.gruppe == "flaeche" and w.rest(jetzt) > 0 for w in self.aktiv):
                self._ausloesen(regel, jetzt, ich=True)

    def gruppe_lp(self, eid: int, anteil: float) -> None:
        """Mitspieler unter 25 % LP einmal melden, erst nach Erholung ueber 50 % wieder."""
        if anteil > LP_WIEDER:
            self._knapp.discard(eid)
            return
        if not self.an or anteil >= LP_KNAPP or eid in self._knapp:
            return
        self._knapp.add(eid)
        with self.lock:
            self._hinzufuegen(GRUPPE_LP, self.uhr(), ziel=self.zustand.spieler.get(eid, ""))

    def _hinzufuegen(self, regel: Regel, start: float, ich: bool = False, ziel: str = "") -> None:
        if regel.gruppe in self.k["meldung_aus"]:
            return  # auf der NexBoard-Seite abgeschaltet
        alt = [w for w in self.aktiv if w.regel.gruppe == regel.gruppe and w.rest(start) > -1.2]
        if any(w.regel == regel and start - w.start < 1.0 for w in alt):
            return  # derselbe Skill doppelt: nur einmal warnen
        seit = min([w.seit for w in alt] + [start])
        self.aktiv = [w for w in self.aktiv if w.regel.gruppe != regel.gruppe]
        warnung = Warnung(regel, start, ich, seit, ziel)
        self.aktiv.append(warnung)
        art = self.k["warnton"].get(regel.gruppe, "ansage")
        if art != "aus":
            self.laut.append((art, warnung.titel().replace(tr("  –  DU!"), tr(" auf dir"))))

    def schnappschuss(self) -> list[Warnung]:
        jetzt = self.uhr()
        with self.lock:
            for t, r in [g for g in self.geplant if g[0] <= jetzt]:
                self.geplant.remove((t, r))
                self._hinzufuegen(r, t)
            self.aktiv = [w for w in self.aktiv if w.rest(jetzt) > -1.2]
            return list(self.aktiv)

    def letzte(self, jetzt: float) -> Warnung | None:
        """Die zuletzt erschienene Warnung, die gerade laeuft (fuer die Todesursache). Lernhilfe zaehlt nicht."""
        with self.lock:
            laufend = [w for w in self.aktiv if w.regel.gruppe != "casts" and w.start <= jetzt
                       and w.rest(jetzt) > -1.2]
        return max(laufend, key=lambda w: w.start, default=None)

    def vorschau(self) -> list[tuple[str, float]]:
        """Kleine Zeile oben: (Text, Sekunden). 0 Sekunden = jetzt moeglich."""
        jetzt = self.uhr()
        with self.lock:
            liste = [(r.titel.replace(" kommt", "").replace(" erwartet", ""), t + r.vorlauf - jetzt)
                     for t, r in self.geplant if r.gruppe not in self.k["meldung_aus"]]
        if "regen" in self.k["meldung_aus"]:
            self.regen_zuletzt = None
        if self.regen_zuletzt is not None and not any(t.startswith("Regen") for t, _ in liste):
            seit = jetzt - self.regen_zuletzt
            if seit < REGEN_PAUSE:
                liste.append(("Regen des Hasses frühestens", REGEN_PAUSE - seit))
            elif seit < REGEN_PAUSE + REGEN_FENSTER:
                liste.append(("Regen des Hasses jederzeit möglich", 0.0))
            else:
                self.regen_zuletzt = None  # Kampf vermutlich vorbei
        for ende in list(self.zustand.berserker.values()):  # 0x8D21: Boss wird berserk
            if ende > jetzt:
                liste.append(("Berserker", ende - jetzt))
        return sorted(liste, key=lambda x: x[1])


def cast_regel(skill: int, npc: int) -> Regel:
    """Graue Anzeige fuer einen Boss-Cast ohne eigene Regel (Dungeons ohne Warnungen)."""
    sprache = konfig_laden()["sprache"]
    boss = npc_name(npc, sprache) or "Boss"
    return Regel(a2_namen("skills", sprache).get(str(skill), str(skill)), f"{boss} · {skill}",
                 3.0, GRAU, "casts")


def gesprochen(text: str) -> Path | None:
    """Wav-Datei mit dem gesprochenen Text. Wird beim ersten Mal mit Piper erzeugt (ca. 0,4 s)."""
    sprache = konfig_laden()["sprache"]
    datei = ANSAGEN / sprache / (hashlib.md5(text.encode()).hexdigest() + ".wav")
    if not datei.exists():
        programm = PIPER / "piper" / "piper"
        if not programm.exists():
            return None
        datei.parent.mkdir(parents=True, exist_ok=True)
        neu = datei.with_suffix(f".{threading.get_ident()}.tmp")
        subprocess.run([programm, "-m", PIPER / "stimmen" / f"{STIMMEN[sprache]}.onnx", "-f", neu],
                       input=text.encode(), capture_output=True)
        if not neu.exists():
            return None
        neu.replace(datei)
    return datei


def ansage(text: str) -> None:
    """Spricht den Text, ohne zu warten. Ohne Piper gibt es den Piepton."""
    threading.Thread(target=lambda: abspielen(gesprochen(text) or ALARM), daemon=True).start()


def ansagen_vorbereiten() -> None:
    """Alle festen Ansagen vorab erzeugen, damit sie im Kampf sofort kommen."""
    titel = {r.titel for r in (*REGELN.values(), *STATUS_REGELN.values(), GROGGY)} | {flamme(0).titel,
                                                                                    REGEN_KOMMT.titel}
    texte = [tr(t) for t in titel] + [tr(REGELN[TODESMAL].titel) + tr(" auf dir")]
    threading.Thread(target=lambda: [gesprochen(t) for t in texte], daemon=True).start()


def alarm_abspielen() -> None:
    if not ALARM.exists():
        ALARM.parent.mkdir(parents=True, exist_ok=True)
        rate, daten = 44100, bytearray()
        for ton in (988, 740, 988, 740):
            for i in range(int(rate * 0.11)):
                t = i / rate
                huelle = min(1.0, t * 80, (0.11 - t) * 80)
                daten += int(0.6 * 32767 * huelle * math.sin(2 * math.pi * ton * t)).to_bytes(
                    2, "little", signed=True)
        with wave.open(str(ALARM), "wb") as w:
            w.setnchannels(1)
            w.setsampwidth(2)
            w.setframerate(rate)
            w.writeframes(bytes(daten))
    abspielen(ALARM)
