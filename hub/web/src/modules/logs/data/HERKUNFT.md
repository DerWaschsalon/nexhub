Spieldaten für das Modul Logs aus A2Tools-DPS-Meter (https://github.com/taengu/A2Tools-DPS-Meter, GPL-3.0), `src/data/`:

- `skill_icons.json`: Skill-Code (erste vier Ziffern) → Bildname auf dem Spiel-CDN
- `skills/<sprache>.json`: Skill-Code → Name (`i18n/skills/`)
- `buffs/<sprache>.json`: Buff-ID → Name (`i18n/abnormals/`)
- `buffs/icons.json`: Buff-ID → Bildname, aus `abnormals.json` (nur das Feld `icon`)

Die Inhalte stammen aus AION 2 (NCSOFT). Zum Aktualisieren die Dateien aus einer neueren A2Tools-Version kopieren.

Figuren der Klassen in `hub/web/static/klassen/figur/` (freigestellte Renderbilder von NCSOFT, wie sie
auch die offizielle Klassenseite zeigt), am 11.11.2026 übernommen von Questlog
(`https://cdn.questlog.gg/aion-2/assets/classes/<klasse>.webp`); `elementalist` heißt im Hub `spiritmaster`.
Für den Faustkämpfer gibt es dort noch keine Figur. `ranger-<platz>.webp` (Waffe, Stiefel, Handschuhe, Gürtel,
Schultern, Brust, Hose, Helm, Umhang) sind jeweils nur dieser Platz aus `ranger.webp`, ausgeschnitten mit
Segment Anything von Meta (Apache-2.0) über `hub/tools/figure_layers.py`, für das Leuchten beim Zeigen.
