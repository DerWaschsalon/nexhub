Spieldaten aus A2Tools-DPS-Meter (https://github.com/taengu/A2Tools-DPS-Meter, GPL-3.0), `src/data/`:

- `skill_icons.json`: Skill-Code (erste vier Ziffern) → Bildname auf dem Spiel-CDN
- `skills/<sprache>.json`: Skill-Code → Name (`i18n/skills/`)
- `buffs/<sprache>.json`: Buff-ID → Name (`i18n/abnormals/`)
- `buffs/icons.json`: Buff-ID → Bildname, aus `abnormals.json` (nur das Feld `icon`)

Die Inhalte stammen aus AION 2 (NCSOFT). Zum Aktualisieren die Dateien aus einer neueren A2Tools-Version kopieren.
