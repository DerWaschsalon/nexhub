# nexproto

Gemeinsame Formate für NexBoard-Daemon, Hub und Bot. Jede Definition steht genau einmal hier als
Pydantic-Modell; Python-Programme im Repo importieren das Paket direkt, alle anderen nutzen das
daraus erzeugte JSON-Schema unter [`schema/`](schema/).

| Format | Modul | Schema | Wofür |
|---|---|---|---|
| NexLog v1 | `nexproto/nexlog.py` | `schema/nexlog-v1.schema.json` | ein Dungeon-Run vom Daemon an den Hub |

Das Protokoll zwischen Daemon und Touch-Leiste steht weiter in
[`nexboard/docs/protocol.schema.json`](../nexboard/docs/protocol.schema.json).

## NexLog v1

Ein Run, so wie der Daemon ihn nach dem Ende hochlädt: **eine** gzip-gepackte JSON-Datei.

```json
{
  "format": "nexlog",
  "version": 1,
  "recorder": {"nexboard": "0.5.0", "capture": "<build-id>", "language": "en"},
  "run": {"dungeon_id": 600123, "dungeon": "Ferocious Horn Den", "difficulty": "Normal",
          "start_ms": 1792000120000, "end_ms": 1792000450000, "complete": true,
          "bosses_total": 3, "bosses_killed": 3},
  "you": {"name": "Testheld", "cls": "ranger"},
  "names": {"Mo***n|cleric": "Moonlin"},
  "fights": [ { "id": "auto_…", "bossName": "…", "actors": […], "details": {…}, "buffs": […], … } ],
  "hits": { "auto_…": { "version": 1, "fight": "auto_…", "target": 37797, "start_ms": …,
                        "columns": ["t_ms","actor","owner","skill","damage","multi","flags"],
                        "flags": {"crit": 1, "back": 2, …, "dot": 1024},
                        "rows": [[1520, 8731, 0, 17030000, 31332, 0, 3], …] } }
}
```

| Feld | Inhalt |
|---|---|
| `recorder` | Versionen von Daemon und Mitschnitt, Sprache der Namen in `fights` |
| `run` | Zusammenfassung, wie der Daemon sie heute schon bildet (`runs.py`, `bot.run_payload`): Dungeon englisch und sprachunabhängig, Zeiten in Unix-ms, besiegte Bosse |
| `you` | eigener Charakter des Aufnehmenden, wenn bekannt; damit verknüpft der Hub Charakter und Konto |
| `names` | aufgelöste Namen der Mitspieler. Der Mitschnitt speichert fremde Namen maskiert („Mo\*\*\*n“), der Daemon kennt die vollen aus dem Live-Stream. Schlüssel wie in `runs.yaml`: `Maske|Klasse` |
| `fights` | die Kampfdateien des Mitschnitts (`~/.local/share/deckbar/aion2/history/*.json`), **unverändert** im Format des A2Tools-Meters, 1 bis 64 Stück |
| `hits` | **jeder einzelne Treffer** je Kampf-ID, so wie `deckbar-capture` ihn nach `hits/<id>.json` schreibt (siehe unten); fehlt für Kämpfe ohne Treffer-Datei |

Regeln:
- Alle Kämpfe stammen aus dem Dungeon des Runs; `hits` gehört nur zu Kämpfen aus `fights`.
- Das Modell prüft von den Kampfdateien nur, was der Hub sicher braucht (`id`, `bossName`,
  `mobCode`, `dungeonId`, `startTimeMs`, `durationMs`, `actors`, `details`). Alles andere geht
  unverändert durch, damit eine neue Meter-Version nichts kaputt macht.
- Grenzen: gepackt höchstens 8 MB, entpackt höchstens 32 MB (Schutz gegen Entpackbomben).
- Eine inkompatible Änderung bekommt `version: 2`; `unpack()` lehnt unbekannte Versionen ab.

```python
from nexproto import NexLog, NexLogError, pack, unpack

data = pack(log)          # NexLog → bytes (gzip)
log = unpack(data)        # bytes → NexLog, sonst NexLogError mit lesbarem Grund
```

### Einzeltreffer (`hits`)

Eine Zeile pro Treffer, Zeit relativ zum Kampfbeginn:

| Spalte | Inhalt |
|---|---|
| `t_ms` | ms seit Kampfbeginn (`start_ms`) |
| `actor` | Figur, die getroffen hat (`actorId` wie in `actors`) |
| `owner` | bei Beschwörungen die Figur dahinter, sonst 0 – gezählt wird `owner or actor` |
| `skill` | Code wie in `details.skills[].code` der Kampfdatei; dort steht auch der Name |
| `damage` | Schaden inklusive Mehrfachtreffer |
| `multi` | Anzahl der Mehrfachtreffer |
| `flags` | Merkmale als Bits, die Namen stehen in `flags` (crit, back, frontal, perfect, double, parry, shield_block, iron_wall, regeneration, perfect_block, dot) |

Woher: Das A2Tools-Meter zählt Treffer nur zusammen (Schaden pro Fähigkeit, Zeitpunkte pro
Treffer). Ein kleiner Haken im Kern ([`nexboard/capture/patches/`](../nexboard/capture/patches/),
`capture/build.sh` wendet ihn an) meldet jeden Treffer an `deckbar-capture`, das beim Speichern
eines Kampfes `hits/<id>.json` neben `history/<id>.json` schreibt. Gegenprobe mit einem echten
Dungeon-Abend (13 Kämpfe, 28 000 Treffer, abgespielt mit `deckbar-capture --replay`): Schaden,
Trefferzahl und Krits stimmen pro Figur, Fähigkeit und DoT exakt mit den Summen des Meters überein.

### Warum Kampfdateien plus Treffer statt eines reinen Ereignisstroms

Die Kampfdateien enthalten schon alles, was das Meter für seine Detailansicht braucht (Quoten pro
Fähigkeit, Heilung, Buffs mit Zeitabschnitten, Tode, Ping, maximale Boss-HP, Ausrüstung). Sie
unverändert mitzuschicken heißt: nichts geht verloren, und der Hub kann später mehr auswerten,
ohne dass sich das Format ändert. Die Treffer ergänzen genau das, was dort fehlt.

### Gemessen (21.10.2026)

Mit `tools/nexlog_messen.py` an einer echten Kampf-History (gamunex): 244 Kämpfe, daraus 24 Dungeon-Runs
(grob gruppiert, < 20 min Pause im selben Dungeon), jeder als NexLog gepackt, entpackt und geprüft.
Diese History stammt noch von vor dem Treffer-Haken, die Werte sind also **ohne** `hits`:

| | Median | p90 | Maximum |
|---|---|---|---|
| Kämpfe je Run | 6 | 21 | 26 |
| roh | 406 KB | 1,7 MB | 2,6 MB |
| gepackt (gzip -6) | 57 KB | 309 KB | 467 KB |
| Packen | 8 ms | 46 ms | 72 ms |

Die Treffer kosten gepackt rund 16 KB je Kampf (Abspiel-Test: 18 KB ohne, 34 KB mit). Ein
typischer Run mit 6 Kämpfen landet damit bei etwa 160 KB, der größte gemessene bei etwa 900 KB.

zstd -3 war praktisch gleich groß (55 KB im Median), zstd -19 rund 30 % kleiner, aber knapp
zehnmal langsamer. gzip gewinnt, weil es in Python und im Browser eingebaut ist und keine weitere
Abhängigkeit braucht. Bei 90 Tagen Aufbewahrung und einigen Runs am Tag bleiben die Rohdaten im
Bereich weniger hundert MB.

Datenschutz: Die Kampfdateien enthalten Name, Klasse, Ausrüstungswert und Server-IDs aller
Spieler im Kampf. In Dungeons ist das die eigene Gruppe (bis 8 Spieler gemessen). Weltbosse
(Dungeon 0, bis über 200 Spieler) sind keine Runs und werden nicht hochgeladen.

## Entwickeln

```
cd proto && uv sync
uv run pytest -q                    # Tests (nur erfundene Daten)
uv run python -m nexproto.schema    # schema/*.json nach Änderungen am Modell neu schreiben
uv run python tools/nexlog_messen.py ~/.local/share/deckbar/aion2/history
```

Echte Kampfdateien enthalten Mitspielernamen und gehören nie ins Repo.
