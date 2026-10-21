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
  "fights": [ { "id": "auto_…", "bossName": "…", "actors": […], "details": {…}, "buffs": […], … } ]
}
```

| Feld | Inhalt |
|---|---|
| `recorder` | Versionen von Daemon und Mitschnitt, Sprache der Namen in `fights` |
| `run` | Zusammenfassung, wie der Daemon sie heute schon bildet (`runs.py`, `bot.run_payload`): Dungeon englisch und sprachunabhängig, Zeiten in Unix-ms, besiegte Bosse |
| `you` | eigener Charakter des Aufnehmenden, wenn bekannt; damit verknüpft der Hub Charakter und Konto |
| `names` | aufgelöste Namen der Mitspieler. Der Mitschnitt speichert fremde Namen maskiert („Mo\*\*\*n“), der Daemon kennt die vollen aus dem Live-Stream. Schlüssel wie in `runs.yaml`: `Maske|Klasse` |
| `fights` | die Kampfdateien des Mitschnitts (`~/.local/share/deckbar/aion2/history/*.json`), **unverändert** im Format des A2Tools-Meters, 1 bis 64 Stück |

Regeln:
- Alle Kämpfe stammen aus dem Dungeon des Runs.
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

### Warum so und nicht als Ereignisstrom

Geplant war ein eigener Ereignisstrom (ein Eintrag pro Treffer). Der Mitschnitt schreibt aber
heute schon pro Bosskampf eine Datei mit allem, was das A2Tools-Meter für seine eigene
Detailansicht braucht: Schaden und Trefferquoten pro Spieler und Fähigkeit, Zeitpunkte jedes
Treffers, Heilung, Buffs mit Zeitabschnitten, Tode, Ping, maximale Boss-HP, Ausrüstungswert.
Diese Dateien unverändert einzupacken heißt: keine Änderung am Rust-Mitschnitt, nichts geht
verloren, und der Hub kann später mehr auswerten, ohne dass Clients neu ausgerollt werden müssen.

Was fehlt: der Schaden **jedes einzelnen** Treffers (es gibt Zeitpunkte pro Treffer, aber Schaden
nur pro Fähigkeit). Für DPS-Kurven reicht das; braucht eine Auswertung später doch Einzeltreffer,
kommt das als `version: 2` mit einem Zusatzfeld aus dem Mitschnitt.

### Gemessen (21.10.2026)

Mit `tools/nexlog_messen.py` an einer echten Kampf-History (gamunex): 244 Kämpfe, daraus 24 Dungeon-Runs
(grob gruppiert, < 20 min Pause im selben Dungeon), jeder als NexLog gepackt, entpackt und geprüft.

| | Median | p90 | Maximum |
|---|---|---|---|
| Kämpfe je Run | 6 | 21 | 26 |
| roh | 406 KB | 1,7 MB | 2,6 MB |
| gepackt (gzip -6) | 57 KB | 309 KB | 467 KB |
| Packen | 8 ms | 46 ms | 72 ms |

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
