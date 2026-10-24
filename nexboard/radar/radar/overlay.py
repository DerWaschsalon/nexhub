"""Radar-Overlay (PySide6): Nord oben, Spieler in der Mitte."""
from __future__ import annotations

import json
import math
import os
import shutil
import subprocess
import time
import wave
from pathlib import Path

from PySide6.QtCore import QPointF, QRectF, Qt, QTimer
from PySide6.QtGui import QAction, QColor, QFont, QPainter, QPen
from PySide6.QtWidgets import QMenu, QWidget

from .zustand import Cube, RadarZustand

KONFIG = Path.home() / ".config" / "aion2-radar.json"
TON = Path.home() / ".cache" / "aion2-radar" / "ping.wav"
REICHWEITEN = (50, 100, 150, 300, 600)

# Standardwerte stehen in standard.json, damit der NexBoard-Daemon dieselben nutzt
STANDARD = json.loads((Path(__file__).parent / "standard.json").read_text())

FARBE_GRUND = QColor(10, 16, 28)
FARBE_RING = QColor(70, 90, 120)
FARBE_ICH = QColor(0, 230, 118)
FARBE_CUBE = QColor(255, 82, 82)
FARBE_GRUPPE = QColor(80, 170, 255)
FARBE_FELDBOSS = QColor(186, 85, 255)
FARBE_OEFFNEN = QColor(255, 160, 40)
FARBE_TEXT = QColor(220, 228, 240)
FARBE_LEISE = QColor(120, 135, 160)


_konfig: dict | None = None


def konfig_laden() -> dict:
    """Gemeinsames Einstellungs-dict fuer alle Fenster (nur einmal gelesen)."""
    global _konfig
    if _konfig is None:
        try:
            _konfig = {**STANDARD, **json.loads(KONFIG.read_text())}
        except (OSError, ValueError):
            _konfig = dict(STANDARD)
    return _konfig


def konfig_neu_laden() -> dict:
    """Datei neu lesen (nach einer Aenderung auf der NexBoard-Seite). Aendert dasselbe dict, das
    alle Fenster halten."""
    k = konfig_laden()
    try:
        neu = json.loads(KONFIG.read_text())
    except (OSError, ValueError):
        return k
    k.clear()
    k.update({**STANDARD, **neu})
    return k


def konfig_speichern(k: dict) -> None:
    try:
        KONFIG.parent.mkdir(parents=True, exist_ok=True)
        tmp = KONFIG.with_suffix(".tmp")  # erst ganz schreiben, dann ersetzen: der Daemon liest nie eine halbe Datei
        tmp.write_text(json.dumps(k, indent=2))
        os.replace(tmp, KONFIG)
    except OSError:
        pass


def ton_erzeugen() -> Path:
    if not TON.exists():
        TON.parent.mkdir(parents=True, exist_ok=True)
        rate, daten = 44100, bytearray()
        for i in range(int(rate * 0.22)):
            t = i / rate
            huelle = math.exp(-t * 14)
            wert = int(0.5 * 32767 * huelle * math.sin(2 * math.pi * 1250 * t))
            daten += wert.to_bytes(2, "little", signed=True)
        with wave.open(str(TON), "wb") as w:
            w.setnchannels(1)
            w.setsampwidth(2)
            w.setframerate(rate)
            w.writeframes(bytes(daten))
    return TON


def ton_abspielen() -> None:
    spieler = shutil.which("pw-play") or shutil.which("paplay")
    if spieler:
        subprocess.Popen([spieler, str(ton_erzeugen())],
                         stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)


class RadarFenster(QWidget):
    def __init__(self, zustand: RadarZustand, quelle, karte, warnung) -> None:
        super().__init__()
        self.zustand = zustand
        self.quelle = quelle
        self.karte = karte
        self.warnung = warnung
        self.k = konfig_laden()
        self._zieh_start: QPointF | None = None

        self.setWindowTitle("AION2 Radar")
        self.setWindowFlags(Qt.FramelessWindowHint | Qt.WindowStaysOnTopHint | Qt.Tool)
        self.setAttribute(Qt.WA_TranslucentBackground)
        self.setWindowOpacity(self.k["deckkraft"])
        g = self.k["groesse"]
        self.setGeometry(self.k["x"], self.k["y"], g, g + 34)

        zustand.bei_neuem_cube.append(self._neuer_cube)
        self._ton_faellig = False
        self._dungeon: str | None = None
        self._gemeldet: set = set()  # Feldboss-Ansagen, die schon kamen
        self._sekunde = 0
        self.timer = QTimer(self)
        self.timer.timeout.connect(self._takt)
        self.timer.start(100)

    # --- Ereignisse -------------------------------------------------------

    def _neuer_cube(self, cube: Cube) -> None:
        self._ton_faellig = True  # kommt aus dem Mitschnitt-Thread

    def _takt(self) -> None:
        dungeon = self.zustand.dungeon
        if dungeon != self._dungeon:  # Dungeon betreten oder verlassen
            self._dungeon = dungeon
            if not dungeon:
                self.quelle.aufnahme_stoppen()
            elif self.k["aufnahme_auto"]:
                self.quelle.aufnahme_starten(dungeon)  # Lernmodus: jeder Lauf eine eigene Datei
        if int(time.time()) != self._sekunde:
            self._sekunde = int(time.time())
            from .uebersicht import feldboss_ansagen
            feldboss_ansagen(self.zustand, self._gemeldet)
        if self._ton_faellig:
            self._ton_faellig = False
            if self.k["ton"]:
                ton_abspielen()
        self.update()

    def mousePressEvent(self, e) -> None:
        if e.button() == Qt.LeftButton:
            self._zieh_start = e.globalPosition() - QPointF(self.pos())

    def mouseMoveEvent(self, e) -> None:
        if self._zieh_start is not None:
            self.move((e.globalPosition() - self._zieh_start).toPoint())

    def mouseReleaseEvent(self, e) -> None:
        if self._zieh_start is not None:
            self._zieh_start = None
            self.k["x"], self.k["y"] = self.x(), self.y()
            konfig_speichern(self.k)

    def wheelEvent(self, e) -> None:
        i = REICHWEITEN.index(self.k["reichweite"]) if self.k["reichweite"] in REICHWEITEN else 2
        i = max(0, min(len(REICHWEITEN) - 1, i + (-1 if e.angleDelta().y() > 0 else 1)))
        self.k["reichweite"] = REICHWEITEN[i]
        konfig_speichern(self.k)
        self.update()

    def contextMenuEvent(self, e) -> None:
        m = QMenu(self)
        ton = QAction("Ton", m, checkable=True, checked=self.k["ton"])
        ton.toggled.connect(lambda v: self._setzen("ton", v))
        m.addAction(ton)
        m.addAction("Ton testen", ton_abspielen)
        ka = QAction("Karte", m, checkable=True, checked=self.karte.isVisible())
        ka.toggled.connect(self._karte_umschalten)
        m.addAction(ka)
        dreh = m.addMenu("Ausrichtung drehen")
        for grad in (0, 90, 180, 270):
            a = QAction(f"{grad}°", dreh, checkable=True, checked=self.k["drehung"] == grad)
            a.triggered.connect(lambda _=False, g=grad: self._setzen("drehung", g))
            dreh.addAction(a)
        sp = QAction("Spiegeln (Ost/West)", m, checkable=True, checked=self.k["spiegeln"])
        sp.toggled.connect(lambda v: self._setzen("spiegeln", v))
        m.addAction(sp)
        dk = m.addMenu("Deckkraft")
        for wert in (0.5, 0.7, 0.85, 1.0):
            a = QAction(f"{int(wert * 100)} %", dk)
            a.triggered.connect(lambda _=False, w=wert: self._deckkraft(w))
            dk.addAction(a)
        m.addAction("Feldbosse und Vertraute …", self._uebersicht_zeigen)
        wm = m.addMenu("Boss-Warnungen")
        wa = QAction("An", wm, checkable=True, checked=self.warnung.zentrale.an)
        wa.toggled.connect(self._warnung_an)
        wm.addAction(wa)
        wm.addAction("Meldungen auswählen …", self._meldungen_zeigen)
        au = QAction("Aufnahme (Lernmodus)", wm, checkable=True, checked=bool(self.quelle.aufnahme))
        au.toggled.connect(lambda an: self.quelle.aufnahme_starten(self.zustand.dungeon or "dungeon")
                           if an else self.quelle.aufnahme_stoppen())
        wm.addAction(au)
        wm.addAction("Testen", self.warnung.test)
        wm.addAction("Position ändern", self.warnung.verschieben_umschalten)
        m.addSeparator()
        m.addAction("Beenden", self.close)
        m.exec(e.globalPos())

    def _karte_umschalten(self, an: bool) -> None:
        self.karte.setVisible(an)
        self._setzen("karte_offen", an)

    def _uebersicht_zeigen(self) -> None:
        from .uebersicht import UebersichtFenster
        self.uebersicht = UebersichtFenster(self.zustand)
        self.uebersicht.show()

    def _meldungen_zeigen(self) -> None:
        from .warnung import MeldungenFenster
        self.meldungen = MeldungenFenster(self.zustand.dungeon)
        self.meldungen.show()

    def _warnung_an(self, an: bool) -> None:
        self.warnung.zentrale.an = an
        self._setzen("warn_an", an)

    def _setzen(self, schluessel: str, wert) -> None:
        self.k[schluessel] = wert
        konfig_speichern(self.k)
        self.update()

    def _deckkraft(self, w: float) -> None:
        self.setWindowOpacity(w)
        self._setzen("deckkraft", w)

    def closeEvent(self, e) -> None:
        self.karte._geometrie_merken()
        self.karte.deleteLater()
        self.warnung.deleteLater()
        self.quelle.stoppen()
        super().closeEvent(e)

    # --- Zeichnen ---------------------------------------------------------

    def _auf_schirm(self, dx: float, dy: float) -> tuple[float, float]:
        """Weltversatz (cm) -> Bildschirmversatz (rechts, unten). Norden ist Welt -y, Osten +x
        (im Spiel an der Minikarte gemessen vom Projekt aion2cubedetector, bis 2026-10-24 hier +x = Nord)."""
        sx, sy = dx, dy
        if self.k["spiegeln"]:
            sx = -sx
        w = math.radians(self.k["drehung"])
        return sx * math.cos(w) - sy * math.sin(w), sx * math.sin(w) + sy * math.cos(w)

    def paintEvent(self, _) -> None:
        s = self.zustand.schnappschuss()
        g = self.k["groesse"]
        r = g / 2 - 4
        mitte = QPointF(g / 2, g / 2)
        reichweite_cm = self.k["reichweite"] * 100
        mass = (r - 10) / reichweite_cm

        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)

        p.setPen(QPen(FARBE_RING, 1.5))
        p.setBrush(FARBE_GRUND)
        p.drawEllipse(mitte, r, r)
        p.setBrush(Qt.NoBrush)
        p.setPen(QPen(FARBE_RING, 1, Qt.DashLine))
        p.drawEllipse(mitte, r / 2, r / 2)
        p.drawLine(QPointF(mitte.x(), mitte.y() - r + 8), QPointF(mitte.x(), mitte.y() + r - 8))
        p.drawLine(QPointF(mitte.x() - r + 8, mitte.y()), QPointF(mitte.x() + r - 8, mitte.y()))

        klein = QFont("Sans", 7)
        p.setFont(klein)
        p.setPen(FARBE_LEISE)
        nx, ny = self._auf_schirm(0, -1)
        n = QPointF(mitte.x() + nx / math.hypot(nx, ny) * (r - 9), mitte.y() + ny / math.hypot(nx, ny) * (r - 9))
        p.drawText(QRectF(n.x() - 8, n.y() - 7, 16, 14), Qt.AlignCenter, "N")
        p.drawText(QRectF(0, mitte.y() + r - 22, g, 12), Qt.AlignCenter, f"{self.k['reichweite']} m")

        pos = s["position"]
        naechster = None
        if pos:
            for c in s["cubes"]:
                dx, dy, dz = c.x - pos[0], c.y - pos[1], c.z - pos[2]
                dist = math.sqrt(dx * dx + dy * dy + dz * dz)
                ox, oy = self._auf_schirm(dx * mass, dy * mass)
                aussen = math.hypot(ox, oy) > r - 10
                if aussen:
                    f = (r - 10) / math.hypot(ox, oy)
                    ox, oy = ox * f, oy * f
                punkt = QPointF(mitte.x() + ox, mitte.y() + oy)
                if naechster is None or dist < naechster[0]:
                    naechster = (dist, dz, punkt, c.seit, c.oeffner)
                farbe = FARBE_OEFFNEN if c.oeffner else FARBE_CUBE  # orange: jemand oeffnet ihn gerade
                p.setPen(QPen(farbe, 2))
                p.setBrush(Qt.NoBrush if aussen else farbe)
                p.drawEllipse(punkt, 5, 5)
            # Gruppenmitglieder (kommen nur alle 2 s, also grob)
            p.setFont(QFont("Sans", 7))
            for name, x, y, _, _ in s["gruppe"]:
                ox, oy = self._auf_schirm((x - pos[0]) * mass, (y - pos[1]) * mass)
                if math.hypot(ox, oy) < r - 10:
                    punkt = QPointF(mitte.x() + ox, mitte.y() + oy)
                    p.setPen(Qt.NoPen)
                    p.setBrush(FARBE_GRUPPE)
                    p.drawEllipse(punkt, 4, 4)
                    p.setPen(FARBE_GRUPPE)
                    p.drawText(QRectF(punkt.x() - 30, punkt.y() + 4, 60, 10), Qt.AlignCenter, name[:8])
            # lebende Feldbosse der aktuellen Karte als Raute
            for boss in s["feldbosse"]:
                ox, oy = self._auf_schirm((boss["pos"][0] - pos[0]) * mass, (boss["pos"][1] - pos[1]) * mass)
                if math.hypot(ox, oy) < r - 10:
                    x, y = mitte.x() + ox, mitte.y() + oy
                    p.setPen(QPen(FARBE_FELDBOSS, 2))
                    p.setBrush(FARBE_FELDBOSS)
                    p.drawPolygon([QPointF(x, y - 6), QPointF(x + 6, y), QPointF(x, y + 6), QPointF(x - 6, y)])
            if naechster:
                p.setPen(QPen(FARBE_CUBE, 1, Qt.DotLine))
                p.drawLine(mitte, naechster[2])
            p.setPen(Qt.NoPen)
            p.setBrush(FARBE_ICH)
            p.drawEllipse(mitte, 5, 5)

        # Statuszeile unter dem Radar
        p.setPen(Qt.NoPen)
        p.setBrush(FARBE_GRUND)
        p.drawRoundedRect(QRectF(8, g - 1, g - 16, 33), 8, 8)
        p.setFont(QFont("Sans", 9, QFont.Bold))
        p.setPen(FARBE_TEXT)
        zeile1 = QRectF(0, g, g, 16)
        if naechster:
            alter = int(time.time() - naechster[3])
            text = f"Cube: {naechster[0] / 100:.0f} m ({naechster[1] / 100:+.0f} m) · {alter // 60}:{alter % 60:02}"
            if naechster[4]:
                text = f"Cube wird geöffnet: {naechster[4]}"
            if len(s["cubes"]) > 1:
                text += f"  · {len(s['cubes'])} Cubes"
            p.setPen(FARBE_CUBE)
            p.drawText(zeile1, Qt.AlignCenter, text)
        elif s["cubes"] and not pos:
            p.drawText(zeile1, Qt.AlignCenter, f"{len(s['cubes'])} Cube(s), eigene Position fehlt")
        else:
            p.setPen(FARBE_LEISE)
            p.drawText(zeile1, Qt.AlignCenter, "kein Cube in Sicht")
        p.setFont(klein)
        p.setPen(FARBE_LEISE)
        p.drawText(QRectF(0, g + 17, g, 14), Qt.AlignCenter, self._status(s))
        p.end()

    def _status(self, s: dict) -> str:
        if self.quelle.fehler:
            return f"Fehler: {self.quelle.fehler}"
        if not s["nachrichten"]:
            return "warte auf Spieldaten …"
        if s["eid"] is None:
            return "suche eigenen Charakter …"
        alter = s["position_alter"]
        pos = "keine Position" if alter is None else (
            "Position aktuell" if alter < 5 else f"Position vor {alter:.0f} s")
        quelle = "Name" if s["eid_ueber_name"] else "geschätzt"
        text = f"ID {s['eid']} ({quelle}) · {pos}"
        if s["dungeon"]:
            ende = self.zustand.dungeon_ende
            rest = f" {int(ende - time.time()) // 60}:{int(ende - time.time()) % 60:02}" \
                if ende and ende > time.time() else ""
            text = f"{s['dungeon']}{rest} · " + text
        return ("● REC · " if self.quelle.aufnahme else "") + text
