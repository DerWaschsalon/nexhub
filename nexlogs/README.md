# NexLogs

Log-Ansicht für AION-2-Runs, ähnlich Warcraft Logs: Rangliste, DPS-Verlauf, Fähigkeiten und Tode je
Boss. React 19 + TypeScript + Vite, ohne weitere Bibliotheken.

NexLogs hat kein eigenes Backend. Die Runs lädt NexBoard in den Hub hoch; NexLogs liest sie über
die Hub-API (`/api/runs`, `/api/runs/{id}`, `/api/runs/{id}/fights/{kampf}`, geteilt:
`/api/public/runs/{token}`). Der Hub liefert den Build unter `/logs/` aus (`HUB_LOGS_DIR`, im Image
schon gesetzt), damit das Login-Cookie des Hubs gilt.

| Pfad | Inhalt |
|---|---|
| `/logs/` | alle Runs (mit Login) |
| `/logs/run/<id>` | ein Run: Gesamt und je Boss |
| `/logs/run/<id>/kampf/<kampf>` | ein Kampf: Schaden, Fähigkeiten, Tode |
| `/logs/r/<token>` | geteilter Run ohne Login |

## Klassen und Fähigkeiten

- Klassenfarben und -symbole wie im Meter A2Tools-DPS-Meter (GPL-3.0): Farben in
  `src/lib/classes.ts`, Symbole in `public/klassen/` (Herkunft dort in `HERKUNFT.md`).
- Fähigkeitssymbole kommen vom CDN des Spiels (`assets.playnccdn.com`), Zuordnung Code → Bild wie
  in A2Tools: `src/data/skill_icons.json` plus Regeln in `src/lib/skillIcons.ts`.
- Im DPS-Verlauf hat jeder Spieler seine Klassenfarbe; ein zweiter Spieler derselben Klasse ist
  gestrichelt.

## Entwickeln

```
npm ci
npm run dev      # http://localhost:5174/logs/, /api geht an den Hub auf localhost:8000
npm run build    # prüft die Typen und baut nach dist/
```

Für echte Daten den Hub lokal starten (`hub/README.md`) und dort anmelden.
