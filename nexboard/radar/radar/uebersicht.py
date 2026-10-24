"""Fenster "Feldbosse und Vertraute": Respawn-Timer der Feldbosse, Riss-Zeitplan und Seelen-Stand der Vertrauten."""
from __future__ import annotations

import time
from datetime import datetime, timezone

from PySide6.QtCore import Qt, QTimer
from PySide6.QtGui import QColor
from PySide6.QtWidgets import (QCheckBox, QComboBox, QHBoxLayout, QLabel, QTableWidget, QTableWidgetItem,
                               QTabWidget, QVBoxLayout, QWidget)

from .daten import VERTRAUTE, npc_name
from .overlay import konfig_laden, konfig_speichern
from .warnung import ansage, tr

VERMUTLICH_DA = 2 * 3600  # so lange nach dem Respawn gilt ein Feldboss als "vermutlich da"
GRUEN, ORANGE, GRAU = QColor(0, 230, 118), QColor(255, 160, 40), QColor(140, 150, 170)
SEELEN = (5, 25, 75)  # Seelen fuer Stufe 1, 2 und 3 (MAX), 105 insgesamt (laut aion2pettracker, passt zum Mitschnitt)


# Feste Termine der globalen Server (EU/NA) aus jackships/aion2-data: (Name, Bezugszeit UTC, alle Minuten,
# offen Minuten). In UTC, damit die Zeitumstellung nichts verschiebt. Nur der Riss ist dort "confirmed".
TERMINE = [
    ("Riss", "2026-10-07 00:00", 180, 10),
    ("Shugo-Fest", "2026-10-07 00:00", 60, 10),
    ("Beritra-Luftangriff", "2026-10-07 00:30", 60, 10),
    ("Wächterin Kaira", "2026-10-07 01:00", 180, 30),
    ("Tages-Reset", "2026-10-07 07:00", 1440, 1),
    ("Wochen-Reset", "2026-10-07 07:00", 10080, 1),  # Mittwoch
]


def termin(jetzt: float, bezug: str, alle: int, offen: int) -> tuple[float, bool]:
    """(Beginn des naechsten oder laufenden Termins, gerade offen?)."""
    start = datetime.fromisoformat(bezug).replace(tzinfo=timezone.utc).timestamp()
    beginn = start + -(-(jetzt - start) // (alle * 60)) * alle * 60  # naechster Beginn ab jetzt
    if jetzt < beginn - alle * 60 + offen * 60:
        return beginn - alle * 60, True
    return beginn, False


def riss(jetzt: float) -> tuple[float, bool]:
    return termin(jetzt, *TERMINE[0][1:])


def fehlende_seelen(stufe: int, seelen: int) -> tuple[int, int]:
    """(Seelen bis zur naechsten Stufe, Seelen bis MAX)."""
    if stufe >= 3:
        return 0, 0
    naechste = SEELEN[stufe] - seelen
    return naechste, naechste + sum(SEELEN[stufe + 1:])


def feldboss_name(platz: str, boss: dict) -> str:
    return npc_name(boss["npc"], konfig_laden()["sprache"]) if boss.get("npc") else \
        f"{tr('Feldboss')} {int(platz) % 100}"


def feldboss_text(boss: dict, jetzt: float) -> tuple[str, QColor, float]:
    """(Anzeige, Farbe, Sekunden bis Respawn) fuer einen Feldboss-Platz."""
    rest = boss["zeit"] - jetzt
    if boss["lebt"]:
        return tr("lebt"), GRUEN, 0
    if rest > 0:
        return f"{tr('in')} {int(rest // 3600)}:{int(rest % 3600 // 60):02}:{int(rest % 60):02}", ORANGE, rest
    if boss["zeit"] and -rest < VERMUTLICH_DA:
        return tr("vermutlich da"), GRUEN, 0
    return tr("unbekannt"), GRAU, 1e9


def feldboss_ansagen(zustand, gemeldet: set) -> None:
    """Ansage 5 Minuten vor dem Respawn und beim Respawn, nur fuer die aktuelle Karte."""
    if not konfig_laden()["feldboss_ansage"]:
        return
    jetzt = time.time()
    beginn, _ = riss(jetzt)
    for grenze, satz in ((300, " in 5 Minuten"), (0, " ist offen")):
        if beginn - jetzt <= grenze and ("riss", beginn, grenze) not in gemeldet:
            gemeldet.add(("riss", beginn, grenze))
            if beginn - jetzt > grenze - 30:
                ansage(tr("Riss") + tr(satz))
    for platz, boss in list(zustand.feldbosse.items()):
        rest = boss["zeit"] - jetzt
        if boss["karte"] != zustand.zone or boss["lebt"] or rest < -10:
            continue
        for grenze, satz in ((300, " in 5 Minuten"), (0, " ist da")):
            schluessel = (platz, boss["zeit"], grenze)
            if rest <= grenze and schluessel not in gemeldet:
                gemeldet.add(schluessel)
                if rest > grenze - 30:  # nicht nachtraeglich, z.B. nach dem Einloggen
                    ansage(feldboss_name(platz, boss) + tr(satz))


def tabelle(spalten: tuple[str, ...]) -> QTableWidget:
    t = QTableWidget(0, len(spalten))
    t.setHorizontalHeaderLabels([tr(s) for s in spalten])
    t.verticalHeader().hide()
    t.setEditTriggers(QTableWidget.NoEditTriggers)
    t.horizontalHeader().setStretchLastSection(True)
    return t


def zelle(wert, farbe: QColor | None = None, tipp: str = "") -> QTableWidgetItem:
    """Tabellenzelle. Zahlen bleiben Zahlen, damit das Sortieren stimmt."""
    z = QTableWidgetItem()
    z.setData(Qt.DisplayRole, wert)
    z.setToolTip(tipp)
    if farbe:
        z.setForeground(farbe)
    return z


class UebersichtFenster(QWidget):
    def __init__(self, zustand) -> None:
        super().__init__(None, Qt.WindowStaysOnTopHint)
        self.zustand = zustand
        self.k = konfig_laden()
        self.setWindowTitle(tr("AION2 Feldbosse und Vertraute"))
        self.setStyleSheet("QWidget { background: #0e1420; color: #e6ecf6; font-size: 11pt; }"
                           "QTableWidget { gridline-color: #24304a; }"
                           "QHeaderView::section { background: #18223a; border: none; padding: 4px; }"
                           "QTabBar::tab { padding: 6px 14px; color: #8a96ad; border: none; }"
                           "QTabBar::tab:selected { color: #e6ecf6; border-bottom: 3px solid #00e676; }"
                           "QComboBox { border: 2px solid #5a6a85; border-radius: 6px; padding: 3px 8px; }")
        reiter = QTabWidget()
        QVBoxLayout(self).addWidget(reiter)

        # Feldbosse
        seite = QWidget()
        spalte = QVBoxLayout(seite)
        an = QCheckBox(tr("Ansage 5 Minuten vorher (Feldbosse und Riss)"), checked=self.k["feldboss_ansage"])
        an.toggled.connect(lambda wert: self._merken("feldboss_ansage", wert))
        spalte.addWidget(an)
        self.termine = tabelle(("Termin", "Uhrzeit", "Status"))
        self.termine.setRowCount(len(TERMINE))
        self.termine.setFixedHeight(44 + 30 * len(TERMINE))
        spalte.addWidget(self.termine)
        self.bosse = tabelle(("Feldboss", "Karte", "Status"))
        spalte.addWidget(self.bosse)
        reiter.addTab(seite, tr("Feldbosse"))

        # Vertraute
        seite = QWidget()
        spalte = QVBoxLayout(seite)
        self.filter = QComboBox()
        for text in ("Alle", "Noch nicht MAX", "Nicht angefangen"):
            self.filter.addItem(tr(text), text)
        self.filter.currentIndexChanged.connect(self._vertraute)
        self.arten = QComboBox()
        for text in ("Alle Arten", "Cogni", "Fera", "Natura", "Varian", "Spezial"):
            self.arten.addItem(tr(text), text)
        self.arten.currentIndexChanged.connect(self._vertraute)
        self.summe = QLabel()
        filter_zeile = QHBoxLayout()
        filter_zeile.addWidget(self.filter)
        filter_zeile.addWidget(self.arten)
        spalte.addLayout(filter_zeile)
        spalte.addWidget(self.summe)
        self.liste = tabelle(("Vertrauter", "Art", "Stufe (3 = MAX)", "Seelen", "Fehlen", "Wo farmen"))
        self.liste.setSortingEnabled(True)
        self.liste.sortItems(4, Qt.AscendingOrder)  # zuerst, was der naechsten Stufe am naechsten ist
        spalte.addWidget(self.liste)
        reiter.addTab(seite, tr("Vertraute"))

        self.resize(900, 640)
        self._stand = -1
        self.timer = QTimer(self, interval=1000, timeout=self._takt)
        self.timer.start()
        self._takt()

    def _merken(self, schluessel: str, wert) -> None:
        self.k[schluessel] = wert
        konfig_speichern(self.k)

    def _takt(self) -> None:
        self._feldbosse()
        if self._stand != self.zustand.vertraute_stand:
            self._stand = self.zustand.vertraute_stand
            self._vertraute()

    def _feldbosse(self) -> None:
        jetzt = time.time()
        for nr, (name, bezug, alle, dauer) in enumerate(TERMINE):
            beginn, offen = termin(jetzt, bezug, alle, dauer)
            rest = int(beginn - jetzt)
            tage = f"{rest // 86400} d " if rest >= 86400 else ""
            self.termine.setItem(nr, 0, zelle(tr(name)))
            self.termine.setItem(nr, 1, zelle(datetime.fromtimestamp(beginn).strftime("%a %H:%M")))  # Ortszeit
            self.termine.setItem(nr, 2, zelle(f"{tr('offen bis')} {datetime.fromtimestamp(beginn + dauer * 60):%H:%M}",
                                              GRUEN) if offen else zelle(
                f"{tr('in')} {tage}{rest % 86400 // 3600}:{rest % 3600 // 60:02}:{rest % 60:02}", ORANGE))
        self.termine.resizeColumnsToContents()
        zeilen = []
        for platz, boss in self.zustand.feldbosse.items():
            text, farbe, rest = feldboss_text(boss, jetzt)
            hier = boss["karte"] == self.zustand.zone
            zeilen.append((not hier, rest, feldboss_name(platz, boss), boss["karte"], text, farbe))
        self.bosse.setRowCount(len(zeilen))
        for nr, (_, _, name, karte, text, farbe) in enumerate(sorted(zeilen)):
            self.bosse.setItem(nr, 0, zelle(name))
            self.bosse.setItem(nr, 1, zelle(karte))
            self.bosse.setItem(nr, 2, zelle(text, farbe))
        self.bosse.resizeColumnsToContents()

    def _vertraute(self) -> None:
        sprache, auswahl, art = self.k["sprache"], self.filter.currentData(), self.arten.currentData()
        stand = self.zustand.vertraute
        if not stand:
            self.summe.setText(tr("Noch keine Daten. Sie kommen beim Einloggen oder Zonenwechsel."))
        else:
            fertig = sum(1 for s in stand.values() if s[0] >= 3)
            offen = sum(fehlende_seelen(*stand.get(vid, [0, 0]))[1] for vid in VERTRAUTE)
            self.summe.setText(f"MAX: {fertig}  ·  {tr('angefangen')}: {len(stand)}  ·  "
                               f"{tr('gesamt')}: {len(VERTRAUTE)}  ·  {tr('Seelen bis alles MAX')}: {offen}")
        zeilen = []
        for vid, v in VERTRAUTE.items():
            stufe, seelen = stand.get(vid, [0, 0])
            if (auswahl == "Noch nicht MAX" and stufe >= 3) or (auswahl == "Nicht angefangen" and vid in stand) \
                    or art not in ("Alle Arten", v["art"]):
                continue
            monster = list(dict.fromkeys(npc_name(m, sprache) or "?" for m in v["monster"]))
            zeilen.append((v[sprache], tr(v["art"]), stufe, seelen, fehlende_seelen(stufe, seelen)[0],
                           ", ".join(monster[:3]) or "; ".join(v["orte"][:2]) or "–",
                           "\n".join(monster + v["orte"])))
        self.liste.setSortingEnabled(False)
        self.liste.setRowCount(len(zeilen))
        for nr, (name, typ, stufe, seelen, fehlen, wo, tipp) in enumerate(zeilen):
            self.liste.setItem(nr, 0, zelle(name))
            self.liste.setItem(nr, 1, zelle(typ))
            self.liste.setItem(nr, 2, zelle(stufe, GRUEN if stufe >= 3 else None))
            self.liste.setItem(nr, 3, zelle(seelen))
            self.liste.setItem(nr, 4, zelle(fehlen))
            self.liste.setItem(nr, 5, zelle(wo, tipp=tipp))
        self.liste.setSortingEnabled(True)
        self.liste.resizeColumnsToContents()
