# Hub: Parses in den Logs (Abyss Logs und eigene Runs)

Stand 2026-11-25, Wunsch Navonex.

## Wozu

In der Log-Ansicht des Hubs soll bei jedem Spieler und Boss stehen, wie gut sein DPS war: eine Zahl von 0 bis 100 mit Farbe, wie bei Warcraft Logs. Zwei Vergleiche nebeneinander:

- **EU:** gegen alle Spieler derselben Klasse am selben Boss auf Abyss Logs (Region EU)
- **Gilde:** gegen alle Charaktere derselben Klasse am selben Boss in unseren eigenen Runs im Hub

## Ziele

- Parse je Spieler und Boss in der Run-Ansicht, für eingeloggte Mitglieder und für geteilte Runs (`/r/<token>`)
- Hard und Normal getrennt (bei Abyss Logs hat jede Schwierigkeit eigene Boss-IDs, z. B. Ludra Normal 2301014 in 600082, Hard 2300290 in 600083)
- Abruf bei Abyss Logs langsam und nur für Bosse und Klassen, die in unseren Runs vorkommen

## Nicht-Ziele (erste Fassung)

- Gruppen nach Kampfkraft (die Daten hätten `combatPower`, kommt eventuell später)
- Parse im Bot-Post oder im Overlay
- eigene Seite mit Ranglisten
- Upload zu a2tools.app, NotMeter, Questlog

## Was nicht passieren darf

- Abyss Logs mit Anfragen zuschütten: höchstens eine Anfrage alle 2 Sekunden, jede Rangliste höchstens einmal am Tag
- Hub fällt aus oder Seite hängt, weil Abyss Logs langsam oder weg ist: die Run-Ansicht liest nur gespeicherte Daten, ohne Abruf im Anfragepfad
- fremde Spielernamen von Abyss Logs speichern: gespeichert werden nur DPS-Werte

## Was es heute gibt

- `hub/api/nexhub_api/modules/bis/abysslogs.py`: Abruf der Abyss-Logs-API (`api.abysslogs.com/v1`, inoffiziell, aus dem JS-Bundle gelesen), `leaderboard()`, `best_per_name()`, `MIN_SECONDS = 30`, `abyss_class()`.
- Nachgeprüft am 2026-11-25:
  - `GET /v1/leaderboards?region=eu&class=<Klasse>&boss=<mobCode>&limit=100&page=<n>` liefert `entries`, `total`, `page`, `limit`. Höchstens 100 je Seite, Beispiel Waldläufer an Kromede's Desire: 2.733 Einträge, 28 Seiten.
  - Ein Eintrag enthält `rank`, `playerName`, `classHint`, `gearScore`, `combatPower`, `dps`, `totalDamage`, `combatDuration`, `encounterId`, `verified`, `createdAt`.
  - `GET /v1/bosses?region=eu` liefert 495 Bosse mit `mobCode`, `name`, `category`, `tier`, `dungeonId`.
  - `mobCode` ist dieselbe NPC-ID wie `mob` in unseren Runs, `dungeonId` dieselbe wie bei uns.
- `modules/logs/models.py`: `Run.summary` (aus `analysis.summarize()`) hat `bosses: [{fight, name, mob, start_ms, duration_ms, killed, players: [{name, cls, damage, dps}]}]`.
- Hub-Module (`module.py`): eigene Routen, Tabellen, Hintergrundaufgaben (`start`), Importe nur aus dem Kern und aus `requires`. Geprüft von `tests/test_module_boundaries.py`. Vorbild: Modul `loot` (`requires=("logs",)`).
- Web: `modules/logs/components/RunView.svelte`, `FightView.svelte`, `RankBars.svelte` (Balken je Spieler, Prop `note`).

## Ansätze

- **A (gewählt): Abyss Logs und eigene Runs.** Ranglisten täglich zwischenspeichern, Parse beim Anzeigen aus den gespeicherten Zahlen rechnen, Gildenvergleich aus den Run-Zusammenfassungen.
- **B: nur Abyss Logs.** Weniger Arbeit, aber ohne Gildenvergleich. Verworfen, weil Navonex beides will.
- **Nicht weiter verfolgt:**
  - Nur die Top 100 nehmen, das gäbe nur eine Platzierung statt eines Parses.
  - Bei jedem Seitenaufruf live abrufen, das wäre langsam und brächte zu viele Anfragen.

## Design

### Neues API-Modul `parses`

`hub/api/nexhub_api/modules/parses/`, `requires=("logs", "bis")`. Es nutzt `bis.abysslogs` für den Abruf und `logs.models.Run` für die Runs.

**Tabelle `parse_boards`** (Alembic-Migration):

| Spalte | Inhalt |
|---|---|
| `boss` | int, mobCode |
| `cls` | str, Hub-Klasse |
| `region` | str, `eu` |
| `fetched_at` | Zeitpunkt des Abrufs |
| `total` | Gesamtzahl laut API |
| `dps` | JSON, aufsteigend sortierte Liste der Bestwerte je Spielername |

Eindeutig ist `(boss, cls, region)`.

**Hintergrundaufgabe:**
- Alle 10 Minuten werden die nötigen Paare gesucht: `(mob, cls)` aus `Run.summary.bosses` mit `killed`, Runs der letzten 30 Tage.
- Abgerufen wird, was fehlt oder älter als 24 Stunden ist, ältestes zuerst und höchstens 5 Ranglisten je Durchlauf.
- Alle Seiten werden mit 2 Sekunden Pause dazwischen geholt.
- Kämpfe unter 30 s (`MIN_SECONDS`) fallen weg. Je Spielername zählt der beste Kampf (`best_per_name`).
- Fehler (`AbyssError`) werden geloggt, der alte Stand bleibt stehen.
- Ein Boss ohne Rangliste („not ranked“) wird als leere Liste gespeichert und nicht täglich neu versucht.

**Rechnung:**
- `parse(wert, liste)` ist der Anteil der Werte in der Liste, die kleiner als `wert` sind, mal 100, abgerundet. Ist `wert` größer als alle Werte, ergibt das 100.
- Dafür reicht `bisect` auf der sortierten Liste.
- **EU:** Unser `dps` aus der Run-Zusammenfassung gegen `parse_boards.dps`.
- **Gilde:**
  - Bestwert je Charakter (Name und Klasse) aus allen Runs mit diesem Boss, ohne zeitliche Grenze.
  - Der eigene Charakter zählt mit seinem Bestwert mit.
  - Angezeigt wird der Wert erst ab 10 Charakteren, sonst „zu wenig Daten (n)“.

**Routen:**
- `GET /api/parses/runs/{run_id}` (Login) und `GET /api/public/parses/shared/{token}` (geteilter Run).
- Antwort je Boss-Kampf (`fight`) und Spieler (`name`):

```json
{"eu": 87, "eu_n": 2733, "eu_at": "...", "guild": 60, "guild_n": 12}
```

- `null`, wenn es keinen Wert gibt.
- Rechnet nur aus der Datenbank, ohne Abruf.

### Web

- Neues Web-Modul `parses` mit derselben Kennung (Konvention aus `module.py`), ohne eigene Seite und ohne Menüeintrag.
- Es liefert die Komponente `ParseBadge.svelte` und den API-Aufruf.
- Ob `logs` sie direkt importieren darf, entscheidet der Builder nach den Regeln im Web. Sonst kommt sie in `logs` und nur die API ins Modul.
- In `RankBars` bekommt jeder Spieler hinter dem DPS zwei kleine farbige Zahlen:

```
Navonex   ████████████████  142.300 DPS   EU 87  Gilde 60
Fabio     ██████████████    128.900 DPS   EU 71  Gilde 45
Kantor X  ███████████        98.000 DPS   EU 34  Gilde –
```

- Tooltip: „EU: besser als 87 % von 2.733 Waldläufern auf Abyss Logs (Stand 25.11.)“ und „Gilde: besser als 60 % von 12 Charakteren“.
- Farben wie bei Warcraft Logs:

| Parse | Farbe |
|---|---|
| unter 25 | grau |
| 25 bis 49 | grün |
| 50 bis 74 | blau |
| 75 bis 94 | lila |
| 95 bis 98 | orange |
| 99 | rosa |
| 100 | gold |

- Ohne Wert: „–“ mit Grund im Tooltip.
- Nur bei getöteten Bossen. Ist die Rangliste noch nicht geladen: „EU …“ mit Tooltip „wird geladen“.
- Hinweis auf der Seite „Wie wir bewerten“: Was ein Parse ist, Quelle Abyss Logs (inoffiziell, Messung kann leicht abweichen) und die Gildenbasis.

## Entscheidungen von Claude (bitte prüfen)

- Basis ist der Bestwert je Spielername auf Abyss Logs, nicht jeder einzelne Kampf. Sonst zählen Vielspieler mehrfach.
- Es zählen auch unverifizierte Einträge (`verified: false`). Sonst fallen viele Einträge weg (auf der letzten Seite waren alle unverifiziert).
- Die Gildenschwelle liegt bei 10 Charakteren.
- Abruf nur für Paare aus Runs der letzten 30 Tage, täglich erneuert.
- Nur Region EU.

## Was der Builder entscheidet

- Name und Ort der Hilfsfunktionen, Tests (Rechnung mit Grenzfällen, Abruf mit gefälschtem httpx, Modulgrenzen), genaue Texte (deutsch und englisch über i18n).

## Abstimmung

Fabio baut den Hub gerade um (#164 bis #166). Die Arbeit läuft im Worktree `~/Projekte/nexhub-parses`, Zweig `hub-parses`, auf `origin/main@b9bc9a0`. Vor dem PR wird erneut auf `main` aufgesetzt. Bescheid an Fabio in Issue #69 nur mit Freigabe von Navonex.
