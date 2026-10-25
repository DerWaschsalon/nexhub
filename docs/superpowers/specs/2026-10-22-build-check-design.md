# Build-Check: der eigene Charakter gegen die Top-Spieler seiner Klasse

Stand 22.10.2026 · Wunsch von Navonex · Vorbild: Fabios Bilder „Kantor-Check“ und „Kantor-Build“

## Wozu

Navonex will auf einen Blick sehen, was an seinem Charakter gegenüber den besten Spielern seiner
Klasse fehlt, und zwar konkret: nicht „die Top haben +15“, sondern „nimm auf Ring 1 Todesschuss“,
„23 von 30 tragen Manasteine mit Waffenschaden, legendär“. Was er schon gut hat, soll nicht als
Aufgabe auftauchen. Ganz unten steht, womit er anfangen soll.

Vorbild sind zwei Bilder, die Fabios Claude für dessen Kantor einmalig erstellt hat. Im Repo gibt
es dafür keinen Code. Sie zeigen die Richtung (Aufbau, Tiefe, Ampelfarben, „Reihenfolge für neue
Punkte“), sind aber deutlich umfangreicher als das, was hier als Erstes gebaut wird.

## Drei Teile, in dieser Reihenfolge

1. **Ausrüstung und Werte gegen die Top-Spieler** (dieses Dokument): „Alles, was CP bringt“ mit
   Empfehlungen je Platz.
2. **DPS am Boss** aus den eigenen Runs gegen Abyss Logs (Bild „Kantor-Check“, obere Hälfte).
3. **Punkte-Plan** für Daevanion und Stigmen mit Wegsuche auf dem Brett (Bild „Kantor-Build“).

Teile 2 und 3 bekommen eigene Entwürfe und bauen auf der Vergleichsgruppe aus Teil 1 auf.

## Ziele (Teil 1)

- In der Armory auf einen Charakter gehen, Knopf „Build-Check“ drücken.
- Der Hub stellt die Vergleichsgruppe zusammen, holt deren Profile und vergleicht Feld für Feld.
- Ergebnis ist eine Seite im Hub im Stil der Vorbilder: Ausrüstung um das Charakterbild herum,
  jeder Platz grün, gelb oder rot (Entwurf C aus dem Brainstorming), darunter Arkana, Werte,
  Daevanion, Skills und Titel, ganz unten „Zuerst:“ mit den fünf wichtigsten Schritten.
- Die Seite lässt sich über einen Link teilen, ohne Login, wie Runs und Vergleiche.

## Nicht-Ziele

- **Kein Abruf im Hintergrund.** Ausgelöst wird nur durch den Klick (ausdrücklicher Wunsch).
  Kein täglicher Lauf, kein Vorab-Sammeln für alle Klassen.
- **Keine Bilddatei (PNG).** Die Seite mit Teilen-Link reicht (ausdrücklich bestätigt).
- Kein DPS-Vergleich und kein Punkte-Plan (Teile 2 und 3).
- Keine Namen der Top-Spieler auf der Seite und nicht in der Datenbank; nur Zählungen wie
  „23 von 30“.

## Was es zum Fehlschlag machen würde

- Empfehlungen, die nicht stimmen, weil die Vergleichsgruppe Müll enthält (Kämpfe von 0,01 s,
  falsch aufgelöste Server, Charaktere einer anderen Klasse).
- Eine Seite, die nur Zahlen nebeneinanderstellt und nicht sagt, was zu tun ist.
- Viel neuer Code neben bestehendem, der dasselbe tut (siehe CLAUDE.md, Code-Stil).

## Daten

### Vergleichsgruppe aus Abyss Logs

`https://api.abysslogs.com/v1/leaderboards` (inoffiziell, nicht dokumentiert, aus dem JS-Bundle der
Seite gelesen, Stand 22.10.2026). Parameter: `region=eu`, `class=<Anzeigename>` (z. B. `Ranger`,
Großschreibung zählt; Liste über `/v1/classes?region=eu`), `boss=<mobCode>` (Liste über
`/v1/bosses?region=eu`), dazu `limit`, `page`. Antwort `{entries, total, page, limit}`, je Eintrag
`playerName`, `classHint`, `combatPower`, `gearScore`, `dps`, `combatDuration`, `encounterId`,
`verified`, `createdAt`. **Kein Server.**

Auswahl (Entscheidung Claude, im Bau anpassbar):
- Region EU, Klasse des eigenen Charakters.
- Je Boss der höchsten Stufe eine Abfrage (Fabios Vorbild nimmt T4), Einträge mit
  `combatDuration` unter 30 s verwerfen.
- Nur Einträge mit ähnlicher Kampfkraft (±15 % um die eigene), damit sich die Ausrüstung
  vergleichen lässt. Fabios Vorbild: 134–150k bei 133k eigener. Von Navonex bestätigt (22.10.):
  die Besten auf der eigenen Stufe, nicht die Besten überhaupt.
- Je Name die beste Platzierung, die besten **15** Namen.

### Server auflösen

Über die vorhandene NC-Suche (`NC.search(name, "eu", cls)`): genaue Namensgleichheit und Klasse;
bei mehreren Treffern der mit der nächstliegenden Kampfkraft (aus dem Profil). Nicht eindeutig
auflösbare Namen fallen weg, der nächste rückt nach.

### Profile

`NC.snapshot(server_id, character_id, lang, items=True)` wie bei der Armory, nur Englisch (die
Seite übersetzt Feldnamen ohnehin über die Texte; Gegenstandsnamen stehen in der Sprache des
eigenen Charakters daneben). Eigener Charakter: die Momentaufnahme aus der Armory, vorher wie beim
Knopf „neu abrufen“ aktualisieren, wenn sie älter als 10 Minuten ist.

### Aufwand je Klick

Rund 15 Suchen plus 15 Profile mit Gegenständen (je Profil etwa 30 Anfragen). Bei 0,3 s Pause
(`HUB_AION2_PAUSE`) sind das zwei bis drei Minuten. Der Klick startet deshalb einen Lauf im
Hintergrund (wie `Armory.refresh`), die Seite zeigt den Fortschritt („Profil 7 von 15“) und lädt
das Ergebnis, sobald es fertig ist.

## Vergleich und Empfehlungen

Für jedes Feld bildet der Hub die Verteilung über die Vergleichsgruppe:

- **Zahlen** (Verzauberung, Überschreitung, Werte, offene Knoten, Skill-Stufen, Arkana-Stufe):
  Median und „wie viele von 15 haben mehr als du“.
- **Auswahlen** (Seltenheit, Manastein-Art und -Seltenheit, Gottstein, Zusatzwerte, verstärkter
  Skill, Arkana-Set, Titel, Flügel): die häufigste Wahl mit Anteil, bei Uneinigkeit die zwei
  häufigsten.

Ampel je Platz und Feld:
- grün: auf oder über dem Median bzw. die eigene Wahl gehört zu den häufigsten zwei.
- gelb: unter dem Median, aber mindestens ein Drittel der Gruppe liegt auch dort.
- rot: weniger als ein Drittel der Gruppe liegt so niedrig bzw. die eigene Wahl hat kaum jemand.

**Priorität** einer Empfehlung = Anteil der Gruppe, der es besser hat („27 von 30“). Das ist für
Laien nachvollziehbar und braucht keine Gewichtung je Wert. Die fünf mit dem höchsten Anteil
stehen unter „Zuerst:“. Grüne Felder erzeugen keine Empfehlung.

Was verglichen wird (alles, was die Momentaufnahme schon enthält, siehe `aion2.py`):
- **Ausrüstung je Platz** (`slots.ts`: links, rechts, Arkana): Seltenheit, Verzauberung,
  Überschreitung, Grundwerte, Zusatzwerte, Manasteine (Anzahl, Art, Seltenheit), Gottsteine,
  verstärkte Skills, bei Arkana das Set.
- **Werte** (`stats`), **Daevanion** je Brett (offene Knoten), **Skills** (Stufen, ausgerüstet),
  **Titel** (ausgerüstete), **Flügel**, **Begleiter**, Kampfkraft, Gegenstandsstufe.

## Ablauf und Oberfläche

- Armory-Profilseite (`hub/armory/[id]`): Knopf „Build-Check“ neben „neu abrufen“. Für alle
  Charaktere in der Armory, nicht nur die eigenen (Entscheidung Claude; die Daten sind auf der
  AION-Website öffentlich).
- Seite `hub/armory/[id]/check`: zeigt den letzten Check mit Datum, sonst den Knopf. Läuft gerade
  einer, den Fortschritt. Ein neuer Check ist höchstens alle 10 Minuten je Charakter möglich (wie
  beim Abruf).
- Teilen wie beim Vergleich: Knopf „Teilen“, Link `/c/<token>` ohne Login, `ShareLink.svelte`.
- Aufbau der Seite wie Entwurf C (Brainstorming 22.10., `bild-c-detail.html`), Optik aus dem
  Hub (Glas-Kacheln, vorhandene Komponenten `ItemIcon`, `PlayerName`, `DaevanionBoard`).

## Speichern

Eine Tabelle `build_checks`: `character_id` (Armory, beim Austragen weg), `created_at`,
`status` (läuft/fertig/fehler), `progress`, `error`, `result` (JSON: die Verteilungen und
Empfehlungen, keine Namen, keine Profile der Top-Spieler), `share_token`. Pro Charakter bleibt
nur der letzte Check (Entscheidung Claude, spart Aufräumen). Die Profile der Top-Spieler werden
nach dem Auswerten verworfen.

## Wiederverwenden statt neu bauen

- `NC` (Suche, Momentaufnahme mit Gegenständen, Pausen, Wiederholungen) und `Armory.refresh` als
  Muster für den Lauf im Hintergrund.
- Teilen: wie `Comparison` / `/v/<token>`, Kasten `ShareLink.svelte`, öffentliche Route nach dem
  Muster von `routes/public.py`.
- Ansicht: Komponenten aus `modules/logs` und `modules/armory` (Gegenstände, Brett, Namen).
- Neu ist nur: Abyss-Logs-Client (eine Funktion), Auswahl der Gruppe, Auswertung, Tabelle,
  Seite. Die Auswertung kommt in eine eigene Datei mit Tests gegen erfundene Profile.

## Risiken

- **Abyss Logs ist inoffiziell.** Ändert sich die Schnittstelle, schlägt der Check mit einer klaren
  Meldung fehl, der Rest des Hubs bleibt unberührt. Abfragen nur auf Klick, wenige je Lauf.
- **Server-Auflösung** kann bei häufigen Namen danebenliegen; Klasse und Kampfkraft als Prüfung,
  sonst Name verwerfen.
- **Datenschutz:** Namen der Top-Spieler werden nur zum Abrufen benutzt, nicht gespeichert, nicht
  angezeigt. Datenschutzerklärung um den Build-Check ergänzen (Abruf bei Abyss Logs und NC).

## Dem Bau überlassen

- Genaue Grenzen der Ampel und Mindestdauer der Kämpfe, nach Blick auf echte Daten.
- Welche Bosse als „höchste Stufe“ zählen (aus `/v1/bosses`, Feld `tier`/`category`).
- Texte, Reihenfolge der Kacheln, Darstellung auf schmalen Bildschirmen.
