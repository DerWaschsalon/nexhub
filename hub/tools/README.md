# Werkzeuge für den Hub

## Figur-Ebenen (`figure_layers.py`)

In Armory und BiS-Listen leuchtet beim Zeigen auf die Klassenfigur der Gegenstand selbst, nicht ein Rechteck.
Dafür gibt es je Ausrüstungsplatz ein eigenes Bild, eine **Ebene**: gleich groß wie die Figur, sichtbar ist nur
dieser Platz, der Rest ist durchsichtig. Bisher gibt es Ebenen nur für den Waldläufer.

### Wie es im Hub zusammenspielt

| Datei | Aufgabe |
|---|---|
| `web/static/klassen/figur/<klasse>-<platz>.webp` | die Ebenen, Platz klein geschrieben (`ranger-boots.webp`) |
| `web/src/modules/logs/data/figureZones.ts` | `SLOT_LAYERS`: welche Plätze einer Klasse eine Ebene haben |
| `web/src/modules/logs/classes.ts` | `figureLayer(klasse, platz)`: Pfad der Ebene |
| `web/src/modules/logs/figureMasks.ts` | `FigureMasks`: liest die Deckkraft der Ebenen, findet den Platz unter dem Zeiger |
| `web/src/modules/logs/components/ClassFigure.svelte` | zeichnet Figur und Ebenen, Licht und Animation |

Je Ebene liegen drei Schichten übereinander: der Schein in der Klassenfarbe **hinter** der Figur (nur am Rand
nach außen sichtbar, Hände und Beine werden nicht überstrahlt), darüber die Figur, darüber das aufgehellte Teil
mit einer leichten Färbung in der Klassenfarbe. Die Maus trifft pixelgenau über die Deckkraft der Ebenen. Die
Rechtecke aus `FIGURE_ZONES` bleiben für die Tastatur und für Schmuck (Ohrringe, Kette, Ringe, Armbänder sind
im Bild nur ein paar Pixel groß). Klassen ohne Ebenen sehen aus wie vorher.

### Wie die Ebenen entstehen

`figure_layers.py` schneidet die Plätze mit **Segment Anything** (Meta, Apache-2.0, Modell `vit_b`) aus. Das
Modell läuft lokal auf der CPU, etwa 30 Sekunden für eine Figur. Einrichtung und Aufruf stehen im Kopf der
Datei. Die Umgebung (rund 1,3 GB unter `~/.cache/figur-sam`) braucht nur, wer die Bilder neu erzeugt. Der Hub
selbst braucht nichts davon.

Je Platz stehen in `CLASSES` ein paar **Punkte** im Bild der Figur (Pixel, `1` = gehört dazu, `0` = gehört nicht
dazu) und ein **Rahmen**, in dem das Teil liegt. Das Modell liefert daraus den Umriss. Die Reihenfolge in
`parts` zählt: Jeder Platz bekommt nur Pixel, die noch kein früherer hat, so überschneiden sich die Ebenen nie.

Ablauf im Skript:
1. **Haut zuerst:** Gesicht bis Ausschnitt, Hände und Beine über das Modell, der Arm über die Farbe. Die Haut
   bekommt kein Platz. Ausnahme sind die Handschuhe: Der Waldläufer trägt keine sichtbaren, also leuchten die Hände.
2. **Plätze über das Modell**, abzüglich der Haut. Kleine abgetrennte Stücke einer Maske fallen weg (Splitter an
   Bändern oder Spitze).
3. **Was das Modell nicht sauber trennt, von Hand:** Den dünnen, dunklen Bogen erkennt `vit_b` nur löchrig, er
   kommt aus Umriss und Farbe (`ranger_bow`). Den Arm verwechselt das Modell mit der Spitze des Umhangs, er
   kommt aus der Farb-Hauterkennung (`color_skin`).
4. **Umhang als Rest:** alles hinter und links der Figur, was übrig ist.
5. Weiche Kante (leichter Weichzeichner), dann als WebP speichern.

### Neue Klasse anlegen

1. In `CLASSES` einen Eintrag für die Klasse anlegen, nach dem Muster von `ranger`. Die Punkte am besten auf
   einem vergrößerten Ausschnitt mit Raster ablesen.
2. Skript mit Vorschau starten: `~/.cache/figur-sam/bin/python hub/tools/figure_layers.py <klasse> vorschau.png`.
   Die Vorschau zeigt jeden Platz in eigener Farbe über der Figur. Punkte nachsetzen, bis nichts überlappt und
   keine Haut in einem Platz steckt.
3. Die Plätze in `SLOT_LAYERS` (`figureZones.ts`) eintragen und die Herkunft in `data/HERKUNFT.md` ergänzen.
4. Prüfen: `npm run check`, dann im Browser jeden Platz anfahren und vergrößert ansehen, auch mit Licht.

### Was wir dabei gelernt haben

- **Von Hand gezeichnete Umrisse und Farbregeln reichen nicht.** Das war der erste Versuch. Sobald ein Teil
  leuchtet, sieht man jede gerade Schnittkante und jedes Stück Haut, das mit drin ist. Mit dem Modell wurden
  die Kanten deutlich sauberer.
- **Haut im Schatten** ist für Farbregeln schwer. Unterscheiden lässt sie sich über den Farbton: Bei Haut liegt
  Grün klar über Blau, bei den rosa Metallplatten (Stiefel, Schulter, Gürtelschnalle) ist Grün gleich Blau.
- **Fast schwarz neben fast schwarz** (Strumpfband und Schatten zwischen den Beinen, Kleid und Umhang) trennt
  weder die Farbe noch das Modell zuverlässig. Dort hilft ein harter Rand (`clip`) an einer Stelle, wo beide
  Seiten dunkel sind und die Kante deshalb nicht auffällt.
- **Kein Rand auf dem leuchtenden Teil.** Ein Rand zeichnet die Schnittkanten zu den Nachbarteilen nach. Der
  Schein gehört hinter die Figur.
- **Punkte genau setzen.** Beim Waldläufer lag der Arm 30 Pixel weiter rechts als angenommen. Vor dem
  Setzen die Farben entlang einer Zeile auslesen.
