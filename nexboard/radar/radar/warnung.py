"""Boss-Warnungen: reagiert auf Boss-Skills (0x3802), Status-Effekte (0x382A), Treffer (0x3804)
und die Stagger-Leiste (0xE005). Die Boss-Ansagen aus dem A2Tools-Plugin stehen in ansagen.py.

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
from dataclasses import dataclass, replace
from pathlib import Path

from .daten import a2_namen, npc_name
from .konfig import abspielen, konfig_laden
from .zustand import BOSS_ANSAGEN, BOSSE, MECHANIKEN

ALARM = Path.home() / ".cache" / "aion2-radar" / "alarm.wav"
PIEP = Path.home() / ".cache" / "aion2-radar" / "piep.wav"  # kurz und hoch, z. B. je Welle
ANSAGEN = Path.home() / ".cache" / "aion2-radar" / "ansagen"   # fertig gesprochene Saetze
PIPER = Path.home() / ".local" / "share" / "aion2-radar" / "piper"  # Programm + Stimmen
STIMMEN = {"de": "de_DE-thorsten-medium", "en": "en_US-amy-medium"}

@dataclass(frozen=True)
class Regel:
    titel: str
    hinweis: str
    vorlauf: float                   # Sekunden bis zum Einschlag
    farbe: tuple[int, int, int]
    gruppe: str                      # neue Warnung ersetzt aeltere derselben Gruppe
    danach: tuple["Regel", ...] = ()  # gleichzeitig ausgeloeste Vorhersagen
    plan: tuple[tuple[float, "Regel"], ...] = ()  # (Sekunden spaeter, Regel)
    auf_dir: bool = False            # zielt der Cast auf mich, steht "DU!" im Titel
    auf: str = "du"                  # Status-Effekt zaehlt auf: du, mitspieler, spieler, boss
    hinweis_ich: str = "Weg von der Gruppe!"  # Hinweis, wenn es dich trifft
    # Was gesprochen wird: None = der Titel; sonst diese Texte, der erste wichtig, die weiteren
    # (Zeile des Bosses) duerfen von der naechsten Warnung abgebrochen werden; () = nichts
    sprechen: tuple[str, ...] | None = None


GRUEN = (0, 230, 118)
LILA, ORANGE, GELB, BLAU, ROT, GRAU = ((186, 85, 255), (255, 120, 0), (255, 210, 0),
                                      (80, 170, 255), (255, 70, 70), (160, 170, 190))


FARBEN = {"GRUEN": GRUEN, "LILA": LILA, "ORANGE": ORANGE, "GELB": GELB, "BLAU": BLAU, "ROT": ROT, "GRAU": GRAU}

# Alle Regeln stehen in mechaniken.json (Aufbau dort unter _felder): je Dungeon die Mechaniken, unter „alle“
# die Warnungen jedes Dungeons. Hier steht nur, wie eine Regel ausgelöst und gezeigt wird.
_DATEN: dict = json.loads((Path(__file__).parent / "mechaniken.json").read_text())
HP_TIEF, HP_WIEDER = 0.5, 0.65   # eigene HP: warnen unter 50 %, erneut erst nach ueber 65 %
LP_KNAPP, LP_WIEDER = 0.25, 0.5  # Mitspieler: melden unter 25 % LP, erneut erst nach ueber 50 %
LERNHILFE = "casts"  # Gruppe der grauen Lernhilfe (jeder Boss-Cast ohne eigene Regel)


def nebenregel(d: dict, haupt: dict) -> Regel:
    """Vorhersage zu einer Mechanik; ohne eigene Farbe oder Gruppe gilt die der Mechanik."""
    return Regel(d["titel"], d["hinweis"], d["sekunden"], FARBEN[d.get("farbe", haupt["farbe"])],
                 d.get("gruppe", haupt["gruppe"]))


def mechanik_regel(m: dict) -> Regel:
    """Eine Regel aus mechaniken.json. „danach“ wird als geplante Folge-Warnung derselben Gruppe
    eingehaengt und ersetzt die erste, wenn sie abgelaufen ist."""
    plan = tuple((p["nach"], nebenregel(p, m)) for p in m.get("plan", ()))
    if m.get("danach"):
        plan += ((m["sekunden"], nebenregel({"titel": m["titel"], **m["danach"]}, m)),)
    wann = m.get("wann", {})
    return Regel(m["titel"], m["hinweis"], m["sekunden"], FARBEN[m["farbe"]], m["gruppe"],
                 danach=tuple(nebenregel(z, m) for z in m.get("zugleich", ())), plan=plan,
                 auf=wann.get("auf", "du"), auf_dir=wann.get("auf_dir", False),
                 hinweis_ich=m.get("hinweis_ich", "Weg von der Gruppe!"))


REGELN: dict[int, Regel] = {}          # Skill, den ein Boss beginnt -> Regel
STATUS_REGELN: dict[int, Regel] = {}   # Status-Effekt (0x382A) -> Regel
TREFFER_REGELN: dict[int, Regel] = {}  # Skill, der dich trifft (Pfuetzen, Zonen) -> Regel
STAGGER_REGELN: dict[int, Regel] = {}  # Boss-NPC mit Stagger-Pruefung -> „Jetzt staggern“
FENSTER: dict[int, dict] = {}          # Skill -> Zeitfenster, in dem er fruehestens wiederkommt
for _m in MECHANIKEN:
    _regel, _wann = mechanik_regel(_m), _m["wann"]
    if _wann["art"] == "cast":
        REGELN.update({skill: _regel for skill in _wann["skills"]})
        if "fenster" in _m:
            FENSTER.update({skill: _m["fenster"] for skill in _wann["skills"]})
    elif _wann["art"] == "effekt":
        STATUS_REGELN[_wann["id"]] = _regel
    elif _wann["art"] == "treffer":
        TREFFER_REGELN.update({skill: _regel for skill in _wann["skills"]})
    elif _wann["art"] == "stagger":
        STAGGER_REGELN.update({npc: _regel for npc in _m["bosse"]})
# Warnungen jedes Dungeons: Boss groggy, eigene HP, Mitspieler mit wenig LP, Flaeche unter dir
ALLE: dict[str, Regel] = {a["gruppe"]: mechanik_regel(a) for a in _DATEN["alle"]}
PROBE: int = _DATEN["probe"]  # Skill des Knopfs „Warnung testen“


def schalter() -> dict:
    """Schalter der Seite „Warnungen“: Gruppe -> Name, je Dungeon in der Reihenfolge der Daten, dann die
    Lernhilfe und je Boss mit Ansagen einer; dazu die Warnungen aller Dungeons."""
    dungeons: dict[str, dict[str, str]] = {d["name"]: {} for d in _DATEN["dungeons"]}
    for m in MECHANIKEN:
        dungeons[m["dungeon"]].setdefault(m["gruppe"], m["meldung"])
    for d in _DATEN["dungeons"]:
        if d.get("lernhilfe"):
            dungeons[d["name"]][LERNHILFE] = "Alle Boss-Casts zeigen (Lernhilfe, Bosse ohne Warnungen)"
    for slug in sorted({r["boss"] for r in BOSS_ANSAGEN["rufe"]}):
        boss = BOSS_ANSAGEN["bosse"][slug]
        dungeons.setdefault(boss["dungeon"], {})[ansage_gruppe(slug)] = f"{boss['name']['de']}: Ansagen"
    return {"alle": {a["gruppe"]: a["meldung"] for a in _DATEN["alle"]}, "dungeons": dungeons}


def ansage_gruppe(slug: str) -> str:
    """Schalter der Boss-Ansagen: einer je Boss."""
    return "ansage_" + slug.replace("-", "_")


SCHALTER = schalter()
ALLE_DUNGEONS: dict[str, str] = SCHALTER["alle"]  # gelten in jedem Dungeon
DUNGEONS: dict[str, dict[str, str]] = SCHALTER["dungeons"]  # Dungeon -> {Gruppe: Name}

# Englische Texte (Deutsch ist der Grundtext). Fehlt ein Eintrag, bleibt der deutsche Text.
ENGLISCH: dict[str, str] = dict(_DATEN["en"])
for _m in (*_DATEN["alle"], *MECHANIKEN):
    ENGLISCH.update(_m["en"])
# Skills mit Boss-Ansage: dazu keine graue Lernhilfe mehr
ANSAGE_SKILLS = {r["id"] for r in BOSS_ANSAGEN["rufe"] if r["art"] != "effekt"}
# Lernhilfe (jeden Boss-Cast grau zeigen) gilt fuer Bosse, zu denen es noch keine Cast-Warnung gibt. Die
# Feuertempel-Regeln stehen ohne Boss-IDs, ihre Bosse haben alle Cast-Warnungen.
CAST_BOSSE = {npc for m in MECHANIKEN if m["wann"]["art"] == "cast" for npc in m["bosse"]} | {
    npc for npc, dungeon in BOSSE.items() if dungeon == "Feuertempel"}


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
        self.fenster_seit: dict[int, float] = {}  # Skill mit Zeitfenster -> zuletzt gesehen
        self.laut: list[tuple[str, str]] = []  # (art, text): Piepton oder Ansage, spielt der RadarDienst ab
        self.k = konfig_laden()
        self.an = self.k["warn_an"]
        self.hp_max = 0
        self.hp_tief = False
        self._knapp: set[int] = set()  # Mitspieler, die schon als „wenig LP“ gemeldet sind

    def cast(self, caster: int, skill: int, ziel: int | None) -> None:
        regel = REGELN.get(skill)
        dungeon = self.zustand.dungeon
        lernhilfe = skill not in ANSAGE_SKILLS and self.zustand.bosse.get(caster, 0) not in CAST_BOSSE | {0}
        if not regel and lernhilfe and dungeon:
            regel = cast_regel(skill, self.zustand.bosse[caster])  # Lernhilfe: jeden Boss-Cast zeigen
        if not regel or not self.gruppe_an(regel.gruppe) or self.fremd(ziel):
            return
        jetzt = self.uhr()
        if skill in FENSTER:
            self.fenster_seit[skill] = jetzt
        ich = regel.auf_dir and ziel is not None and ziel == self.zustand.eigene_eid
        name = "" if ich or ziel == self.zustand.eigene_eid else self.zustand.spieler.get(ziel, "")
        with self.lock:
            self._ausloesen(regel, jetzt, ich, name)

    def fremd(self, ziel: int | None) -> bool:
        """Einstellung „Nur was mich betrifft“ und das Ziel ist ein anderer Spieler. Kein Ziel, der Boss
        selbst oder ein unbekanntes Wesen zaehlen nicht als fremd (Flaechen, Angriffe auf alle)."""
        z = self.zustand
        return bool(self.k.get("nur_mich")) and ziel is not None and ziel != z.eigene_eid \
            and ziel in z.spieler

    def zeigen(self, regel: Regel, jetzt: float) -> None:
        """Eine fertige Warnung von aussen (Boss-Ansagen) zeigen und sprechen."""
        with self.lock:
            self._ausloesen(regel, jetzt)

    def gruppe_an(self, gruppe: str) -> bool:
        """Warnungen an und die Gruppe gehoert zum erkannten Dungeon (sonst Skill-ID aus einem anderen)."""
        dungeon = self.zustand.dungeon
        return self.an and not (dungeon and gruppe not in {*DUNGEONS[dungeon], LERNHILFE})

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
        if regel.auf != "boss" and self.fremd(ziel):
            return
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

    def hp(self, wert: int) -> None:
        """Eigene HP: einmal warnen, wenn sie unter die Haelfte fallen."""
        self.hp_max = max(self.hp_max, wert)
        if wert == 0 or wert > self.hp_max * HP_WIEDER:
            self.hp_tief = False
        elif wert < self.hp_max * HP_TIEF and not self.hp_tief:
            self.hp_tief = True
            if self.an and self.zustand.dungeon:
                with self.lock:
                    self._hinzufuegen(ALLE["hp"], self.uhr())

    def groggy(self, boss: int) -> None:
        if self.an:
            with self.lock:
                # gebrochen: „Jetzt staggern“ ist erledigt
                self.aktiv = [w for w in self.aktiv if w.regel not in STAGGER_REGELN.values()]
                self._hinzufuegen(ALLE["groggy"], self.uhr())

    def flaeche(self, skill: int, x: float, y: float, bis: float) -> None:
        """Ein Monster markiert eine Flaeche am Boden. Liegt ihr Mittelpunkt nah an dir, warnen, mit
        Countdown bis zum Einschlag. Groesse und Form sind unbekannt, deshalb ein fester Abstand."""
        pos = self.zustand.position
        if not self.an or pos is None or bis <= 0:
            return
        if math.hypot(x - pos[0], y - pos[1]) > self.k.get("flaeche_m", 6.0) * 100:  # Welt in cm
            return
        regel = replace(ALLE["flaeche"], vorlauf=bis)
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
        if self.k.get("nur_mich"):
            return  # betrifft einen anderen
        with self.lock:
            self._hinzufuegen(ALLE["gruppe_lp"], self.uhr(), ziel=self.zustand.spieler.get(eid, ""))

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
        if art == "ansage" and regel.sprechen is not None:
            # erster Text wichtig ("ansage"), die weiteren duerfen abgebrochen werden ("zeile")
            self.laut += [("ansage" if i == 0 else "zeile", t) for i, t in enumerate(regel.sprechen) if t]
        elif art != "aus":
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
            laufend = [w for w in self.aktiv if w.regel.gruppe != LERNHILFE and w.start <= jetzt
                       and w.rest(jetzt) > -1.2]
        return max(laufend, key=lambda w: w.start, default=None)

    def vorschau(self) -> list[tuple[str, float]]:
        """Kleine Zeile oben: (Text, Sekunden). 0 Sekunden = jetzt moeglich."""
        jetzt = self.uhr()
        with self.lock:
            liste = [(r.titel.replace(" kommt", "").replace(" erwartet", ""), t + r.vorlauf - jetzt)
                     for t, r in self.geplant if r.gruppe not in self.k["meldung_aus"]]
        for skill, fenster in FENSTER.items():
            gruppe = REGELN[skill].gruppe
            if gruppe in self.k["meldung_aus"]:
                self.fenster_seit.pop(skill, None)
            if skill not in self.fenster_seit or any(r.gruppe == gruppe for _, r in self.geplant):
                continue  # nie gesehen, oder die Vorhersage steht schon in der Zeile
            seit = jetzt - self.fenster_seit[skill]
            if seit < fenster["pause"]:
                liste.append((fenster["frueh"], fenster["pause"] - seit))
            elif seit < fenster["pause"] + fenster["offen"]:
                liste.append((fenster["moeglich"], 0.0))
            else:
                del self.fenster_seit[skill]  # Kampf vermutlich vorbei
        for ende in list(self.zustand.berserker.values()):  # 0x8D21: Boss wird berserk
            if ende > jetzt:
                liste.append(("Berserker", ende - jetzt))
        return sorted(liste, key=lambda x: x[1])


def cast_regel(skill: int, npc: int) -> Regel:
    """Graue Anzeige fuer einen Boss-Cast ohne eigene Regel (Dungeons ohne Warnungen)."""
    sprache = konfig_laden()["sprache"]
    boss = npc_name(npc, sprache) or "Boss"
    return Regel(a2_namen("skills", sprache).get(str(skill), str(skill)), f"{boss} · {skill}",
                 3.0, GRAU, LERNHILFE)


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


class Sprecher:
    """Spricht nacheinander statt durcheinander, wie das A2Tools-Plugin: hoechstens zwei Saetze warten,
    ein wichtiger Satz bricht eine noch laufende Boss-Zeile oder einen Rueckstau ab, eine weitere
    Boss-Zeile bei vollem Stau faellt weg. Ohne Piper gibt es den Alarmton."""

    def __init__(self, spielen=abspielen) -> None:
        self.spielen = spielen  # startet das Abspielen und gibt den Prozess zurueck (oder None)
        self.lock = threading.Lock()
        self.warten: list[tuple[str, bool]] = []  # (Text, wichtig)
        self.laeuft: tuple[subprocess.Popen | None, bool] | None = None  # (Prozess, wichtig)
        self.neu = threading.Event()
        threading.Thread(target=self._schleife, daemon=True).start()

    def sagen(self, text: str, wichtig: bool = True) -> None:
        with self.lock:
            stau = self.warten + ([(None, self.laeuft[1])] if self.laeuft else [])
            boss_zeile_dabei = any(not w for _, w in stau)
            if wichtig and (len(stau) >= 2 or boss_zeile_dabei):
                self._abbrechen()
            elif not wichtig and len(stau) >= 2:
                return
            self.warten.append((text, wichtig))
        self.neu.set()

    def _abbrechen(self) -> None:
        """Wartende Saetze verwerfen und den laufenden beenden. Aufruf unter self.lock."""
        self.warten.clear()
        if self.laeuft and self.laeuft[0]:
            self.laeuft[0].terminate()

    def _schleife(self) -> None:
        while True:
            self.neu.wait()
            with self.lock:
                if not self.warten:
                    self.neu.clear()
                    continue
                text, wichtig = self.warten.pop(0)
            prozess = self.spielen(gesprochen(text) or ALARM)
            with self.lock:
                self.laeuft = (prozess, wichtig)
            if prozess:
                prozess.wait()
            with self.lock:
                self.laeuft = None


_SPRECHER: Sprecher | None = None


def ansage(text: str, wichtig: bool = True) -> None:
    """Spricht den Text ueber die gemeinsame Warteschlange, ohne zu warten."""
    global _SPRECHER
    if _SPRECHER is None:
        _SPRECHER = Sprecher()
    _SPRECHER.sagen(text, wichtig)


def ansagen_vorbereiten() -> None:
    """Alle festen Ansagen vorab erzeugen, damit sie im Kampf sofort kommen."""
    regeln = (*REGELN.values(), *STATUS_REGELN.values(), ALLE["groggy"], ALLE["hp"])
    regeln += tuple(r for regel in regeln for r in (*regel.danach, *(folge for _, folge in regel.plan)))
    texte = {tr(r.titel) for r in regeln} | {tr(r.titel) + tr(" auf dir") for r in regeln if r.auf_dir}
    texte |= set(ansage_kurztexte(konfig_laden()["sprache"]))
    threading.Thread(target=lambda: [gesprochen(t) for t in texte], daemon=True).start()


def _toene(datei: Path, toene: tuple[int, ...], laenge: float) -> Path:
    """Wav-Datei mit diesen Toenen nacheinander (Hz, je `laenge` Sekunden), einmal erzeugt."""
    if not datei.exists():
        datei.parent.mkdir(parents=True, exist_ok=True)
        rate, daten = 44100, bytearray()
        for ton in toene:
            for i in range(int(rate * laenge)):
                t = i / rate
                huelle = min(1.0, t * 80, (laenge - t) * 80)
                daten += int(0.6 * 32767 * huelle * math.sin(2 * math.pi * ton * t)).to_bytes(
                    2, "little", signed=True)
        with wave.open(str(datei), "wb") as w:
            w.setnchannels(1)
            w.setsampwidth(2)
            w.setframerate(rate)
            w.writeframes(bytes(daten))
    return datei


def ansage_kurztexte(sprache: str) -> list[str]:
    """Die kurzen Anweisungen der Boss-Ansagen und „Wieder angreifen“ (die langen Boss-Zeilen nicht,
    die werden beim ersten Mal erzeugt, ca. 0,4 s)."""
    texte = [BOSS_ANSAGEN["sicher"][sprache]]
    for ruf in BOSS_ANSAGEN["rufe"]:
        texte += [ruf[k][sprache] for k in ("anweisung",) if k in ruf]
        texte += [ruf["phase"]["anzeige"][sprache]] if "phase" in ruf else []
    return texte


def alarm_abspielen() -> None:
    abspielen(_toene(ALARM, (988, 740, 988, 740), 0.11))


def piep_abspielen() -> None:
    abspielen(_toene(PIEP, (1320,), 0.09))
