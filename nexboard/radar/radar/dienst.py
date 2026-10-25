"""Das Radar ohne Fenster: Mitschnitt, Auswertung, Ton, Ansagen und Aufnahme.

Der NexBoard-Daemon haelt einen RadarDienst, solange AION 2 laeuft, ruft takt() mehrmals pro
Sekunde auf und zeigt stand() als Widgets im Overlay (Radar, Warnungen, Karte).
"""
from __future__ import annotations

import time
from pathlib import Path

from .konfig import konfig_laden, konfig_neu_laden, ton_abspielen
from .punkte import Karte, PunkteDB
from .quelle import Quelle
from .uebersicht import feldboss_ansagen
from .warnung import STATUS_REGELN, TODESMAL, WarnZentrale, alarm_abspielen, ansage, ansagen_vorbereiten, tr
from .zustand import Cube, RadarZustand

LOG = Path.home() / ".local" / "share" / "aion2-radar" / "spawns.jsonl"  # alle Spawns, fuer die Werkzeuge


class RadarDienst:
    def __init__(self, name: str = "", spawn_log: Path | None = LOG) -> None:
        self.k = konfig_laden()
        if spawn_log:
            spawn_log.parent.mkdir(parents=True, exist_ok=True)
        self.zustand = RadarZustand(name, spawn_log, speichern=True)
        self.quelle = Quelle(self.zustand)
        self.punkte = PunkteDB()  # jeder gesehene Cube wird als Spawnpunkt gemerkt
        self.zentrale = WarnZentrale(self.zustand)
        self.zustand.bei_neuem_cube.append(self._neuer_cube)
        self.zustand.bei_cast.append(self.zentrale.cast)
        self.zustand.bei_status.append(self.zentrale.status)
        self.zustand.bei_groggy.append(self.zentrale.groggy)
        self.zustand.status_ids = set(STATUS_REGELN)
        self._ton_faellig = False
        self._dungeon: str | None = None
        self._gemeldet: set = set()  # Feldboss-Ansagen, die schon kamen
        self._sekunde = 0

    def starten(self) -> None:
        ansagen_vorbereiten()
        self.quelle.live_starten()

    def stoppen(self) -> None:
        self.quelle.stoppen()

    def neu_laden(self) -> None:
        """Einstellungen von der NexBoard-Seite uebernehmen."""
        k = konfig_neu_laden()
        self.zentrale.an = k["warn_an"]
        ansagen_vorbereiten()  # falls die Sprache gewechselt hat

    def warnung_testen(self) -> None:
        self.zentrale.cast(0, TODESMAL, self.zustand.eigene_eid)

    def aufnahme_starten(self) -> None:
        self.quelle.aufnahme_starten(self.zustand.dungeon or "dungeon")

    @property
    def aufnahme(self) -> bool:
        return bool(self.quelle.aufnahme)

    def _neuer_cube(self, cube: Cube) -> None:
        # kommt aus dem Mitschnitt-Thread: nur merken, der Ton kommt im naechsten Takt
        self.punkte.eintragen(cube.x, cube.y, cube.z, cube.objekt_id)
        self._ton_faellig = True

    def takt(self) -> None:
        """Was bisher die Fenster in ihrem Takt erledigt haben: Aufnahme, Ansagen, Ton."""
        dungeon = self.zustand.dungeon
        if dungeon != self._dungeon:  # Dungeon betreten oder verlassen
            self._dungeon = dungeon
            if not dungeon:
                self.quelle.aufnahme_stoppen()
            elif self.k["aufnahme_auto"]:
                self.quelle.aufnahme_starten(dungeon)  # Lernmodus: jeder Lauf eine eigene Datei
        if int(time.time()) != self._sekunde:
            self._sekunde = int(time.time())
            feldboss_ansagen(self.zustand, self._gemeldet)
        if self._ton_faellig:
            self._ton_faellig = False
            if self.k["ton"]:
                ton_abspielen()
        self.zentrale.schnappschuss()  # holt faellige Vorhersagen nach vorn, auch ohne Overlay
        while self.zentrale.laut:
            art, text = self.zentrale.laut.pop(0)
            if art == "ansage":
                ansage(text)
            else:
                alarm_abspielen()

    # --- fuer das Overlay -------------------------------------------------

    def stand(self) -> dict:
        """Alles, was die Widgets zeichnen. Weltkoordinaten in cm, Zeiten in Sekunden."""
        s = self.zustand.schnappschuss()
        jetzt = self.zentrale.uhr()
        return {
            "position": s["position"],
            "position_alter": s["position_alter"],
            "cubes": [{"x": c.x, "y": c.y, "z": c.z, "alter": time.time() - c.seit, "oeffner": c.oeffner}
                      for c in s["cubes"]],
            "gruppe": [{"name": name, "x": x, "y": y} for name, x, y, *_ in s["gruppe"]],
            "feldbosse": [b["pos"][:2] for b in s["feldbosse"]],
            "status": self._status(s),
            "warnungen": [self._warnung(w, jetzt) for w in self.zentrale.schnappschuss()[-3:]],
            "vorschau": [[tr(text), rest] for text, rest in self.zentrale.vorschau()],
            "jetzt_text": tr("JETZT"),
            "karte": self.k["karte_name"] or "",
            "karte_offen": s["karte_offen"] and self.k["bei_karte_ausblenden"],  # Overlay ausblenden
            "punkte": len(self.punkte.punkte),  # aendert sich die Zahl, laedt die Karte die Punkte neu
            "einstellungen": {k: self.k[k] for k in ("reichweite", "drehung", "spiegeln", "karte_folgen")},
        }

    @staticmethod
    def _warnung(w, jetzt: float) -> dict:
        return {"titel": w.titel(), "hinweis": tr("Weg von der Gruppe!" if w.ich else w.regel.hinweis),
                "rest": w.rest(jetzt), "vorlauf": w.regel.vorlauf, "farbe": w.regel.farbe,
                "lernhilfe": w.regel.gruppe == "casts"}  # Lernhilfe: echter Vorlauf unbekannt, keine Sekunden

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
            rest = int(ende - time.time()) if ende else 0
            zeitlimit = f" {rest // 60}:{rest % 60:02}" if rest > 0 else ""
            text = f"{s['dungeon']}{zeitlimit} · {text}"
        return ("● REC · " if self.aufnahme else "") + text

    def karte(self) -> dict:
        """Die eingestellte Karte (sonst die einzige vorhandene) mit Eichung, Fundorten,
        Teleportern und den gesehenen Spawnpunkten."""
        alle = Karte.alle()
        name = self.k["karte_name"] or (alle[0].name if len(alle) == 1 else "")
        karte = next((k for k in alle if k.name == name), None)
        if not karte:
            return {"name": ""}
        return {"name": karte.name, "m": karte.eichung.m,
                "fundorte": karte.liste("fundorte.json"), "teleporter": karte.liste("teleporter.json"),
                "symbol": karte.symbol.exists(),
                "punkte": [[p["x"], p["y"], p["quelle"]] for p in self.punkte.alle()]}
