"""Karten-Overlay: Kartenbild mit gesehenen Spawnpunkten, aktiven Cubes, eigener Position und
Cube-Route (die naechsten drei Fundorte, siehe route.py)."""
from __future__ import annotations

import math
import time
from pathlib import Path

from PySide6.QtCore import QPointF, QRectF, Qt, QTimer
from PySide6.QtGui import (QAction, QColor, QFont, QImage, QPainter, QPainterPath,
                           QPen, QPixmap)
from PySide6.QtWidgets import (QFileDialog, QInputDialog, QMenu, QMessageBox, QSizeGrip,
                               QWidget)

from .overlay import konfig_laden, konfig_speichern
from .punkte import Karte, PunkteDB
from .route import Route
from .zustand import RadarZustand

KOPF = 26
FRISCH_S = 5.0  # so alt darf die eigene Position beim Eichen hoechstens sein

GLAS = QColor(14, 20, 32, 225)
RAND = QColor(255, 255, 255, 40)
TEXT = QColor(225, 232, 244)
LEISE = QColor(140, 155, 180)
ICH = QColor(0, 230, 118)
CUBE = QColor(255, 82, 82)
PUNKT_RADAR = QColor(255, 196, 0)
PUNKT_HAND = QColor(200, 210, 230)
EICH = QColor(80, 170, 255)
ROUTE = QColor(245, 185, 65)
ROUTE_LEISE = QColor(245, 185, 65, 110)
ROUTE_DUNKEL = QColor(20, 26, 40)


class KartenFenster(QWidget):
    def __init__(self, zustand: RadarZustand, punkte: PunkteDB) -> None:
        super().__init__()
        self.zustand = zustand
        self.punkte = punkte
        self.k = konfig_laden()
        self.karte: Karte | None = None
        self.route: Route | None = None
        self.pixmap: QPixmap | None = None
        self.zoom = 1.0
        self.versatz = QPointF(0, 0)  # Bildpunkt, der in der Fenstermitte liegt
        self.folgen = self.k["karte_folgen"]
        self.modus: str | None = None  # "eichen" | "punkt"
        self._ziehen: tuple[str, QPointF, QPointF] | None = None
        self.meldung = ""
        self._meldung_bis = 0.0

        self.setWindowTitle("AION2 Karte")
        self.setWindowFlags(Qt.FramelessWindowHint | Qt.WindowStaysOnTopHint | Qt.Tool)
        self.setAttribute(Qt.WA_TranslucentBackground)
        self.setMinimumSize(220, 180)
        self.setMouseTracking(True)
        self.setGeometry(self.k.get("karte_x", 340), self.k.get("karte_y", 40),
                         self.k.get("karte_b", 420), self.k.get("karte_h", 420))
        self.setWindowOpacity(self.k["karte_deckkraft"])
        self.griff = QSizeGrip(self)
        self.griff.resize(16, 16)

        name = self.k.get("karte_name")
        if name:
            self._karte_setzen(Karte(name))
        self.timer = QTimer(self)
        self.timer.timeout.connect(self._takt)
        self.timer.start(150)

    # --- Karte wechseln ---------------------------------------------------

    def _karte_setzen(self, karte: Karte | None) -> None:
        self.karte = karte
        self.route = Route(karte.ordner / "route.json") if karte else None
        self.pixmap = None
        if karte and karte.bild.exists():
            self.pixmap = QPixmap(str(karte.bild))
            self.versatz = QPointF(self.pixmap.width() / 2, self.pixmap.height() / 2)
            self.zoom = min(self.width() / self.pixmap.width(),
                            (self.height() - KOPF) / self.pixmap.height())
        self.k["karte_name"] = karte.name if karte else None
        konfig_speichern(self.k)
        self.update()

    def _takt(self) -> None:
        ich = self._ich_im_bild()
        if ich and self.folgen:
            self.versatz = QPointF(*ich)
        if ich and self.route and self.zustand.schnappschuss()["position_alter"] <= FRISCH_S:
            self.route.position(ich, self._meter_in_px(self.k["route_abstand"]))
        self.update()

    def _ich_im_bild(self) -> tuple[float, float] | None:
        """Eigene Position in Kartenpixeln, falls bekannt und die Karte geeicht ist."""
        position = self.zustand.schnappschuss()["position"]
        if not position or not self._eich_fertig():
            return None
        return self.karte.eichung.welt_zu_bild(*position[:2])

    def _meter_in_px(self, meter: float) -> float:
        e = self.karte.eichung
        return math.dist(e.welt_zu_bild(0, 0), e.welt_zu_bild(meter * 100, 0))

    def _eich_fertig(self) -> bool:
        return bool(self.karte and self.karte.eichung.fertig)

    def _melden(self, text: str, dauer: float = 4.0) -> None:
        self.meldung = text
        self._meldung_bis = time.time() + dauer

    # --- Koordinaten ------------------------------------------------------

    def _mitte(self) -> QPointF:
        return QPointF(self.width() / 2, KOPF + (self.height() - KOPF) / 2)

    def _bild_zu_schirm(self, u: float, v: float) -> QPointF:
        m = self._mitte()
        return QPointF(m.x() + (u - self.versatz.x()) * self.zoom,
                       m.y() + (v - self.versatz.y()) * self.zoom)

    def _schirm_zu_bild(self, p: QPointF) -> tuple[float, float]:
        m = self._mitte()
        return (self.versatz.x() + (p.x() - m.x()) / self.zoom,
                self.versatz.y() + (p.y() - m.y()) / self.zoom)

    def _welt_zu_schirm(self, x: float, y: float) -> QPointF:
        return self._bild_zu_schirm(*self.karte.eichung.welt_zu_bild(x, y))

    # --- Maus -------------------------------------------------------------

    def resizeEvent(self, e) -> None:
        self.griff.move(self.width() - 16, self.height() - 16)
        QTimer.singleShot(500, self._geometrie_merken)

    def mousePressEvent(self, e) -> None:
        pos = e.position()
        if e.button() != Qt.LeftButton:
            return
        if pos.y() < KOPF:
            self._ziehen = ("fenster", e.globalPosition(), QPointF(self.pos()))
        elif self.modus and self.pixmap:
            self._klick_im_modus(pos)
        elif self.pixmap:
            self._ziehen = ("karte", pos, QPointF(self.versatz))

    def mouseMoveEvent(self, e) -> None:
        if not self._ziehen:
            return
        art, start, wert = self._ziehen
        if art == "fenster":
            self.move((wert + e.globalPosition() - start).toPoint())
        else:
            self.folgen = False
            d = (e.position() - start) / self.zoom
            self.versatz = wert - d
            self.update()

    def mouseReleaseEvent(self, e) -> None:
        if self._ziehen and self._ziehen[0] == "fenster":
            self._geometrie_merken()
        self._ziehen = None

    def wheelEvent(self, e) -> None:
        if not self.pixmap:
            return
        unter = self._schirm_zu_bild(e.position())
        faktor = 1.2 if e.angleDelta().y() > 0 else 1 / 1.2
        self.zoom = max(0.05, min(8.0, self.zoom * faktor))
        # Punkt unter der Maus bleibt stehen
        neu = self._schirm_zu_bild(e.position())
        self.versatz += QPointF(unter[0] - neu[0], unter[1] - neu[1])
        self.update()

    def _geometrie_merken(self) -> None:
        self.k.update(karte_x=self.x(), karte_y=self.y(),
                      karte_b=self.width(), karte_h=self.height())
        konfig_speichern(self.k)

    def _klick_im_modus(self, pos: QPointF) -> None:
        u, v = self._schirm_zu_bild(pos)
        if self.modus == "eichen":
            s = self.zustand.schnappschuss()
            if not s["position"] or s["position_alter"] > FRISCH_S:
                self._melden("Position zu alt: kurz sprinten oder springen, dann klicken")
                return
            x, y, _ = s["position"]
            for px, py, *_ in self.karte.eichung.paare:
                if math.dist((px, py), (x, y)) < 2000:
                    self._melden("Zu nah am letzten Eichpunkt, mind. 20 m weiter gehen")
                    return
            self.karte.eichung.hinzufuegen(x, y, u, v)
            self.karte.speichern()
            n = len(self.karte.eichung.paare)
            if n < 2:
                self._melden("Punkt 1 gesetzt. Woanders hinlaufen, dann Punkt 2", 8)
            else:
                self._melden(f"{n} Eichpunkte, Abweichung {self.karte.eichung.fehler_px():.1f} px."
                             " Weitere Punkte machen es genauer.", 8)
        elif self.modus == "punkt":
            if not self._eich_fertig():
                self._melden("Erst eichen")
                return
            x, y = self.karte.eichung.bild_zu_welt(u, v)
            z = self.zustand.position[2] if self.zustand.position else 0.0
            self.punkte.eintragen(x, y, z, quelle="hand")
            self._melden("Spawnpunkt eingetragen (Rechtsklick > Punkte setzen beenden)")
        # beide Modi bleiben aktiv, bis sie im Menue abgeschaltet werden

    # --- Menue ------------------------------------------------------------

    def contextMenuEvent(self, e) -> None:
        klick = e.pos()
        m = QMenu(self)
        m.addAction("Karte laden …", self._karte_laden)
        alle = Karte.alle()
        if alle:
            wahl = m.addMenu("Karte wählen")
            for k in alle:
                a = QAction(k.name, wahl, checkable=True, checked=bool(self.karte and self.karte.name == k.name))
                a.triggered.connect(lambda _=False, k=k: self._karte_setzen(k))
                wahl.addAction(a)
        if self.karte:
            m.addSeparator()
            e1 = QAction("Eichen (Klick = mein Standort)", m, checkable=True,
                         checked=self.modus == "eichen")
            e1.toggled.connect(lambda v: self._modus("eichen" if v else None))
            m.addAction(e1)
            if self.karte.eichung.paare:
                m.addAction("Eichung zurücksetzen", self._eichung_loeschen)
            if self._eich_fertig():
                p1 = QAction("Spawnpunkte von Hand setzen", m, checkable=True,
                             checked=self.modus == "punkt")
                p1.toggled.connect(lambda v: self._modus("punkt" if v else None))
                m.addAction(p1)
                m.addAction("Nächsten Spawnpunkt hier löschen",
                            lambda: self._punkt_loeschen(QPointF(klick)))
                if self.route and self.route.da:
                    m.addAction("Route: Punkt überspringen", self.route.ueberspringen)
                    m.addAction("Route neu starten", self.route.neu_starten)
                f = QAction("Mir folgen", m, checkable=True, checked=self.folgen)
                f.toggled.connect(self._folgen)
                m.addAction(f)
        m.addSeparator()
        dk = m.addMenu("Deckkraft")
        for w in (0.5, 0.7, 0.9, 1.0):
            a = QAction(f"{int(w * 100)} %", dk)
            a.triggered.connect(lambda _=False, w=w: self._deckkraft(w))
            dk.addAction(a)
        m.addAction("Karte ausblenden", self.hide)
        m.exec(e.globalPos())

    def _modus(self, modus: str | None) -> None:
        self.modus = modus
        if modus == "eichen":
            self._melden("Hinlaufen, kurz sprinten, dann auf der Karte auf deinen Standort klicken", 10)
        elif modus == "punkt":
            self._melden("Auf die Karte klicken, um Spawnpunkte einzutragen", 6)

    def _folgen(self, v: bool) -> None:
        self.folgen = v
        self.k["karte_folgen"] = v
        konfig_speichern(self.k)

    def _deckkraft(self, w: float) -> None:
        self.setWindowOpacity(w)
        self.k["karte_deckkraft"] = w
        konfig_speichern(self.k)

    def _eichung_loeschen(self) -> None:
        self.karte.eichung.zuruecksetzen()
        self.karte.speichern()
        self.update()

    def _punkt_loeschen(self, schirm: QPointF) -> None:
        x, y = self.karte.eichung.bild_zu_welt(*self._schirm_zu_bild(schirm))
        # 15 Bildschirmpixel in Weltmass umrechnen
        x2, y2 = self.karte.eichung.bild_zu_welt(*self._schirm_zu_bild(schirm + QPointF(15, 0)))
        if not self.punkte.entfernen(x, y, math.dist((x, y), (x2, y2))):
            self._melden("Kein Spawnpunkt unter der Maus")

    def _karte_laden(self) -> None:
        pfad, _ = QFileDialog.getOpenFileName(self, "Kartenbild wählen", str(Path.home()),
                                              "Bilder (*.png *.jpg *.jpeg *.webp)")
        if not pfad:
            return
        name, ok = QInputDialog.getText(self, "Kartenname", "Name der Karte:", text="Altgard")
        name = name.strip().replace("/", "-")
        if not ok or not name:
            return
        bild = QImage(pfad)
        if bild.isNull():
            QMessageBox.warning(self, "Karte", "Bild konnte nicht gelesen werden.")
            return
        karte = Karte(name)
        karte.ordner.mkdir(parents=True, exist_ok=True)
        bild.save(str(karte.bild), "PNG")
        karte.speichern()
        self._karte_setzen(karte)
        self._modus("eichen")

    # --- Zeichnen ---------------------------------------------------------

    def paintEvent(self, _) -> None:
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        p.setRenderHint(QPainter.SmoothPixmapTransform)
        rahmen = QRectF(0.5, 0.5, self.width() - 1, self.height() - 1)
        form = QPainterPath()
        form.addRoundedRect(rahmen, 14, 14)
        p.fillPath(form, GLAS)
        p.setClipPath(form)

        if self.pixmap:
            o = self._bild_zu_schirm(0, 0)
            p.drawPixmap(QRectF(o.x(), o.y(), self.pixmap.width() * self.zoom,
                                self.pixmap.height() * self.zoom), self.pixmap,
                         QRectF(self.pixmap.rect()))
            if self._eich_fertig():
                self._inhalt_zeichnen(p)
            if self.route:
                self._route_zeichnen(p)
            if self.modus == "eichen":
                p.setPen(QPen(EICH, 2))
                for *_, u, v in self.karte.eichung.paare:
                    q = self._bild_zu_schirm(u, v)
                    p.drawLine(q + QPointF(-6, 0), q + QPointF(6, 0))
                    p.drawLine(q + QPointF(0, -6), q + QPointF(0, 6))
        else:
            p.setPen(LEISE)
            p.setFont(QFont("Sans", 9))
            p.drawText(QRectF(16, KOPF, self.width() - 32, self.height() - KOPF),
                       Qt.AlignCenter | Qt.TextWordWrap,
                       "Noch keine Karte.\nIngame-Karte öffnen, Screenshot machen,\n"
                       "dann Rechtsklick > Karte laden.")

        # Kopfzeile
        p.fillRect(QRectF(0, 0, self.width(), KOPF), QColor(10, 14, 24, 200))
        p.setPen(QPen(RAND, 1))
        p.drawLine(QPointF(10, KOPF), QPointF(self.width() - 10, KOPF))
        p.setPen(TEXT)
        p.setFont(QFont("Sans", 9, QFont.DemiBold))
        titel = self.karte.name if self.karte else "Karte"
        p.drawText(QRectF(12, 0, self.width() - 24, KOPF), Qt.AlignVCenter | Qt.AlignLeft, titel)
        p.setFont(QFont("Sans", 8))
        p.setPen(LEISE)
        p.drawText(QRectF(12, 0, self.width() - 24, KOPF), Qt.AlignVCenter | Qt.AlignRight,
                   self._kopf_status())

        if self.meldung and time.time() < self._meldung_bis:
            p.setFont(QFont("Sans", 9))
            breite = min(self.width() - 24, p.fontMetrics().horizontalAdvance(self.meldung) + 24)
            kasten = QRectF((self.width() - breite) / 2, self.height() - 44, breite, 28)
            p.setPen(Qt.NoPen)
            p.setBrush(QColor(10, 14, 24, 235))
            p.drawRoundedRect(kasten, 10, 10)
            p.setPen(TEXT)
            p.drawText(kasten.adjusted(8, 0, -8, 0), Qt.AlignCenter | Qt.TextWordWrap, self.meldung)

        p.setClipping(False)
        p.setPen(QPen(RAND, 1))
        p.setBrush(Qt.NoBrush)
        p.drawRoundedRect(rahmen, 14, 14)
        p.end()

    def _inhalt_zeichnen(self, p: QPainter) -> None:
        s = self.zustand.schnappschuss()
        for pt in self.punkte.alle():
            q = self._welt_zu_schirm(pt["x"], pt["y"])
            farbe = PUNKT_RADAR if pt["quelle"] == "radar" else PUNKT_HAND
            p.setPen(QPen(farbe, 1.6))
            p.setBrush(Qt.NoBrush)
            p.drawEllipse(q, 4.5, 4.5)
        puls = 0.5 + 0.5 * math.sin(time.time() * 5)
        for c in s["cubes"]:
            q = self._welt_zu_schirm(c.x, c.y)
            halo = QColor(CUBE)
            halo.setAlpha(int(60 + 80 * puls))
            p.setPen(Qt.NoPen)
            p.setBrush(halo)
            p.drawEllipse(q, 9 + 4 * puls, 9 + 4 * puls)
            p.setBrush(CUBE)
            p.drawEllipse(q, 5, 5)
        if s["position"]:
            q = self._welt_zu_schirm(*s["position"][:2])
            farbe = QColor(ICH)
            if s["position_alter"] > 30:
                farbe.setAlpha(110)  # veraltet
            p.setPen(QPen(QColor(255, 255, 255, 200), 1.5))
            p.setBrush(farbe)
            p.drawEllipse(q, 5.5, 5.5)

    def _route_zeichnen(self, p: QPainter) -> None:
        """Offene Fundorte blass, die naechsten drei gold mit 1-2-3, verbunden ab der eigenen
        Position. Ohne Eichung nur die Punkte, die Reihenfolge haengt dann noch an der Position."""
        naechste = self.route.naechste(3)
        p.setPen(Qt.NoPen)
        p.setBrush(ROUTE_LEISE)
        for u, v in self.route.offene()[len(naechste):]:
            p.drawEllipse(self._bild_zu_schirm(u, v), 3.5, 3.5)
        if not naechste:
            return
        ich = self._ich_im_bild()
        linie = ([self._bild_zu_schirm(*ich)] if ich else []) + [self._bild_zu_schirm(u, v) for u, v in naechste]
        p.setPen(QPen(ROUTE, 2))
        p.drawPolyline(linie)
        p.setFont(QFont("Sans", 8, QFont.Bold))
        for nummer, (u, v) in enumerate(naechste, 1):
            q = self._bild_zu_schirm(u, v)
            erster = nummer == 1
            p.setPen(QPen(ROUTE, 1.5))
            p.setBrush(ROUTE if erster else ROUTE_DUNKEL)
            p.drawEllipse(q, 8, 8)
            p.setPen(ROUTE_DUNKEL if erster else ROUTE)
            p.drawText(QRectF(q.x() - 8, q.y() - 8, 16, 16), Qt.AlignCenter, str(nummer))

    def _kopf_status(self) -> str:
        if self.modus == "eichen":
            n = len(self.karte.eichung.paare) if self.karte else 0
            return f"Eichen: {n} Punkt(e)"
        if self.modus == "punkt":
            return "Punkte setzen"
        if self.karte and not self.karte.eichung.fertig:
            return "nicht geeicht"
        aktiv = len(self.zustand.schnappschuss()["cubes"])
        if self.route and self.route.da:
            gesamt = len(self.route.punkte)
            return f"Route {gesamt - self.route.uebrig}/{gesamt} · {aktiv} aktiv"
        n = len(self.punkte.alle())
        return f"{n} Spawnpunkte · {aktiv} aktiv"

    def closeEvent(self, e) -> None:
        self._geometrie_merken()
        e.ignore()
        self.hide()
