"""Das Radar ohne Fenster: Mitschnitt, Auswertung, Ton, Ansagen und Aufnahme.

Der NexBoard-Daemon haelt einen RadarDienst, solange AION 2 laeuft, ruft takt() mehrmals pro
Sekunde auf und zeigt stand() als Widgets im Overlay (Radar, Warnungen, Karte).
"""
from __future__ import annotations

import time
from collections import deque
from pathlib import Path

from .konfig import konfig_laden, konfig_neu_laden, ton_abspielen
from .punkte import Karte, PunkteDB
from .quelle import Quelle
from .uebersicht import feldboss_ansagen
from .warnung import (STATUS_REGELN, TODESMAL, TREFFER_REGELN, WarnZentrale, alarm_abspielen, ansage,
                      ansagen_vorbereiten, tr)
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
        self.zustand.bei_hp.append(self.zentrale.hp)
        self.zustand.bei_staggern.append(self.zentrale.staggern)
        self.zustand.bei_treffer.append(self.zentrale.treffer)
        self.zustand.bei_gruppe_lp.append(self.zentrale.gruppe_lp)
        self.zustand.bei_tod.append(self._tod)
        self.zustand.bei_flaeche.append(self.zentrale.flaeche)
        # Tode von dir und Mitspielern durch Monster, fuer den Run im Hub (der Daemon liest sie aus)
        self.tode: deque[dict] = deque(maxlen=200)
        self.zustand.status_ids = set(STATUS_REGELN)
        self.zustand.treffer_ids = set(TREFFER_REGELN)
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

    def pvp_neu(self) -> None:
        """PvP-Sitzung neu beginnen (Kills, Tode, Punkte ab jetzt)."""
        self.zustand.pvp.zuruecksetzen()

    def aufnahme_starten(self) -> None:
        self.quelle.aufnahme_starten(self.zustand.dungeon or "dungeon")

    @property
    def aufnahme(self) -> bool:
        return bool(self.quelle.aufnahme)

    def kampf(self) -> dict:
        """Fuer eigene Makros (GET /api/radar/kampf): Boss groggy und die laufenden Warnungen mit
        Gruppe (Schalter auf der NexBoard-Seite), Titel, ob sie dich trifft, und Restzeit. Abgeschaltete
        Warnungen (Seite „Radar“) kommen auch hier nicht vor."""
        jetzt = self.zentrale.uhr()
        return {"groggy": self.zustand.boss_groggy(),
                "warnungen": [{"gruppe": w.regel.gruppe, "titel": w.titel(), "ich": w.ich,
                               "rest": round(w.rest(jetzt), 2)}
                              for w in self.zentrale.schnappschuss() if w.regel.gruppe != "casts"]}

    def _tod(self, opfer: int, skill: int, taeter_name: str) -> None:
        """Tod merken mit Skill und der Warnung, die das Radar gerade zeigte. PvP (Taeter ist ein
        Spieler) und tote Monster zaehlen nicht."""
        z = self.zustand
        name = z.spieler.get(opfer) or (z.charname if opfer == z.eigene_eid else "")
        if taeter_name or not name:
            return
        jetzt = self.zentrale.uhr()
        w = self.zentrale.letzte(jetzt)
        self.tode.append({"t_ms": int(jetzt * 1000), "name": name, "skill": skill,
                          "warning": tr(w.regel.titel) if w else None,
                          "lead_ms": int((jetzt - w.start) * 1000) if w else None})

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
            "kurs": s["kurs"],
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
            "einstellungen": {k: self.k[k] for k in ("reichweite", "drehung", "spiegeln", "karte_folgen", "kurs_oben")},
            "pvp": self.zustand.pvp.stand(),
        }

    @staticmethod
    def _warnung(w, jetzt: float) -> dict:
        return {"titel": w.titel(), "hinweis": tr(w.regel.hinweis_ich if w.ich else w.regel.hinweis),
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
        quelle = "sicher" if s["eid_sicher"] else "geschätzt"
        text = f"ID {s['eid']} ({quelle}) · {pos}"
        if s["dungeon"]:
            ende = self.zustand.dungeon_ende
            rest = int(ende - time.time()) if ende else 0
            zeitlimit = f" {rest // 60}:{rest % 60:02}" if rest > 0 else ""
            text = f"{s['dungeon']}{zeitlimit} · {text}"
        if self.zustand.schluessel:
            text += f" · {self.zustand.schluessel} Cube-Schlüssel benutzt"
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
