"""Cube-Karte von aion2hub holen: Kartenbild, Cube-Fundorte und Teleporter fuer das Kartenfenster.

    python3 -m werkzeuge.cubekarte            # Altgard
    python3 -m werkzeuge.cubekarte --neu      # Eichung neu setzen (eigene Eichung weg)

Legt unter ~/.local/share/aion2-radar/karten/Altgard/ bild.png, eichung.json, fundorte.json,
teleporter.json und teleporter.png (Symbol aus dem Spiel) an.
Nichts davon kommt ins Repo (Daten und Bilder gehoeren aion2hub). Danach im Kartenfenster:
Rechtsklick > Karte wählen > Altgard. Eichen ist nicht noetig, die Umrechnung steht fest (MITTE_PX).

Die Seite liefert ihre Marker im Next.js-Bundle mit, ein Skript pro Karte. Dessen Name aendert sich
bei jedem Update der Seite, deshalb wird er ueber die Ladetabelle DATA_LOADERS gesucht.
"""
from __future__ import annotations

import argparse
import json
import re
import sys
import urllib.request

from PySide6.QtGui import QImage, QPainter

from radar.punkte import Karte

SEITE = "https://aion2hub.com"
KARTEN = {"Altgard": "World_D_A"}
KACHELN = 8          # 8 x 8 Kacheln zu je 1024 px
KACHEL_PX = 512      # verkleinert gespeichert: 4096 px Kantenlaenge reichen und sparen Speicher
KACHEL_ORIGINAL = 1024
# aion2hub-Karten: 1 px = 1 m, Weltursprung in der Kartenmitte, Welt-y zeigt im Bild nach unten.
# Gemessen an drei Teleportern in Altgard (Nornir Assembly, Shulak Street Stall, Basfelt Waterfall):
# Massstab 0,997, Drehung -0,7 Grad, Abweichung 7-14 m. Damit braucht es keine Eichung im Spiel.
# Die Marker der Seite zaehlen y von unten (Leaflet), das Bild von oben, daher v = Kante - y.
MITTE_PX = KACHELN * KACHEL_ORIGINAL / 2
TELEPORTER_SYMBOL = "/maps-assets/UI/Resource/Texture/Icon/UT_Marker_TeleportArtifact_Dark_Engraved.webp"


def laden(pfad: str) -> bytes:
    anfrage = urllib.request.Request(SEITE + pfad, headers={"User-Agent": "Mozilla/5.0"})
    with urllib.request.urlopen(anfrage, timeout=30) as antwort:
        return antwort.read()


def skripte(pfad: str) -> list[str]:
    html = laden(pfad).decode()
    return sorted(set(re.findall(r"/_next/static/chunks/[\w-]+\.js", html)))


def daten_skript(karte: str) -> str:
    """Text des Skripts mit den Markern der Karte."""
    for skript in skripte(f"/maps?map={karte}"):
        text = laden(skript).decode()
        modul = re.search(karte + r":\(\)=>e\.A\((\d+)\)", text)
        if "DATA_LOADERS" in text and modul:
            datei = re.search(modul.group(1) + r',e=>\{e\.v\(t=>Promise\.all\(\["(static/chunks/[\w-]+\.js)"', text)
            if datei:
                return laden("/_next/" + datei.group(1)).decode()
    raise SystemExit("Ladetabelle der Karten nicht gefunden, hat sich die Seite geändert?")


def marker(skript: str, art: str) -> list[tuple[str, int, int]]:
    """Name und Bildposition aller Marker einer Art, z.B. hiddenCube oder teleport."""
    funde = re.findall(r'"n":"((?:[^"\\]|\\.)*)","c":"\w+","s":"' + art + r'","x":(-?\d+),"y":(-?\d+)', skript)
    kante = 2 * MITTE_PX
    # Namen stehen als JS-Text drin (Galorik\\'s); manche Marker stehen doppelt drin
    return sorted({(n.replace("\\'", "'"), int(x), kante - int(y)) for n, x, y in funde})


def kartenbild(karte: str) -> QImage:
    bild = QImage(KACHELN * KACHEL_PX, KACHELN * KACHEL_PX, QImage.Format_RGB32)
    maler = QPainter(bild)
    for zeile in range(KACHELN):
        for spalte in range(KACHELN):
            kachel = QImage.fromData(laden(f"/api/map-tile/{karte}/{karte}_{spalte:02d}_{zeile:02d}.webp"))
            maler.drawImage(spalte * KACHEL_PX, zeile * KACHEL_PX,
                            kachel.scaled(KACHEL_PX, KACHEL_PX))
        print(f"  Kacheln {zeile + 1}/{KACHELN}")
    maler.end()
    return bild


def eichen(karte: Karte, massstab: float) -> None:
    """Feste Umrechnung Welt (cm) -> Kartenbild als drei Eichpunkte speichern."""
    karte.eichung.zuruecksetzen()
    for x, y in ((0, 0), (100_000, 0), (0, 100_000)):
        u = (MITTE_PX + x / 100) * massstab
        v = (MITTE_PX + y / 100) * massstab
        karte.eichung.hinzufuegen(x, y, u, v)
    karte.speichern()


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--karte", default="Altgard", choices=sorted(KARTEN))
    ap.add_argument("--neu", action="store_true",
                    help="Eichung neu setzen (eigene Eichung weg)")
    a = ap.parse_args()
    karte_id = KARTEN[a.karte]
    karte = Karte(a.karte)
    massstab = KACHEL_PX / KACHEL_ORIGINAL

    print("Cube-Fundorte und Teleporter laden …")
    skript = daten_skript(karte_id)
    funde = marker(skript, "hiddenCube")
    teleporter = marker(skript, "teleport")
    print(f"  {len(funde)} Cubes, {len(teleporter)} Teleporter")
    if not karte.bild.exists():
        print("Kartenbild laden …")
        karte.ordner.mkdir(parents=True, exist_ok=True)
        kartenbild(karte_id).save(str(karte.bild), "PNG")

    (karte.ordner / "fundorte.json").write_text(json.dumps([[u * massstab, v * massstab] for _, u, v in funde]))
    (karte.ordner / "teleporter.json").write_text(
        json.dumps([[name, u * massstab, v * massstab] for name, u, v in teleporter], ensure_ascii=False))
    QImage.fromData(laden(TELEPORTER_SYMBOL)).save(str(karte.ordner / "teleporter.png"), "PNG")
    if a.neu or not karte.eichung.fertig:
        eichen(karte, massstab)
        print("Eichung gesetzt.")
    print(f"Fertig: {karte.ordner}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
