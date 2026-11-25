"""Das gemeinsame Aussehen von NexHub und NexBoard: Farben, Flächen, Radien, Schriften.

Die einzige Stelle für diese Werte. `codegen` schreibt daraus je eine tokens.css für das Hub-Web und die
Web-UI der NexBoard; beide Oberflächen nutzen dieselben Namen. Dunkel ist Standard, hell gilt mit
data-theme="light" am <html> (heute nur in der NexBoard umschaltbar).
"""
from __future__ import annotations

# Name der CSS-Variable (ohne --) → Wert. Reihenfolge = Reihenfolge in der Datei.
DARK: dict[str, str] = {
    "bg": "#05060d",
    "text": "#f4f5fa",
    "dim": "rgba(244, 245, 250, 0.66)",  # Nebentext
    "faint": "rgba(244, 245, 250, 0.45)",  # Beschriftungen, Platzhalter
    "accent": "#6ad3ff",
    "accent-2": "#a78bfa",
    "on-accent": "#03131b",  # Schrift auf Akzentflächen
    "ok": "#4ade80",
    "warn": "#fbbf24",
    "danger": "#ff6b6b",
    "info": "#4ea8ff",
    "edge": "rgba(255, 255, 255, 0.14)",
    "edge-soft": "rgba(255, 255, 255, 0.08)",
    # deckende Flächen: Karte ohne Glas, Fläche in der Karte (Eingaben), gewählt/gehovert
    "surface": "#0a0c17",
    "surface-2": "#141829",
    "surface-3": "#1b2036",
    # Glas: durchscheinende Karte (.glass) mit feiner Lichtkante; die Unschärfe bleibt klein
    "glass": "rgba(16, 20, 38, 0.62)",
    "glass-blur": "14px",
    "glass-shine": "rgba(255, 255, 255, 0.06)",
    # helle Schleier auf Flächen (Zeile, Hover) und dunkle Abdeckung (Bild, Schatten)
    "fill": "rgba(255, 255, 255, 0.05)",
    "fill-strong": "rgba(255, 255, 255, 0.1)",
    "shade": "rgba(0, 0, 0, 0.35)",
    "shade-strong": "rgba(0, 0, 0, 0.6)",
    "shade-heavy": "rgba(0, 0, 0, 0.78)",
    "glow": "#0c1030",  # ruhiger Schein im Hintergrund
}
LIGHT: dict[str, str] = {
    "bg": "#e9edf7",
    "text": "#0e1324",
    "dim": "rgba(14, 19, 36, 0.7)",
    "faint": "rgba(14, 19, 36, 0.55)",
    "accent": "#0a6fd6",
    "accent-2": "#6a4ce0",
    "on-accent": "#fff",
    "ok": "#17804a",
    "warn": "#9a5b00",
    "danger": "#c9241c",
    "info": "#0a6fe0",
    "edge": "rgba(14, 19, 36, 0.14)",
    "edge-soft": "rgba(14, 19, 36, 0.08)",
    "surface": "#fff",
    "surface-2": "#f3f5fb",
    "surface-3": "#e6eaf5",
    "glass": "rgba(255, 255, 255, 0.72)",
    "glass-shine": "rgba(255, 255, 255, 0.6)",
    "fill": "rgba(14, 19, 36, 0.04)",
    "fill-strong": "rgba(14, 19, 36, 0.08)",
    "shade": "rgba(14, 19, 36, 0.08)",
    "shade-strong": "rgba(14, 19, 36, 0.3)",
    "shade-heavy": "rgba(14, 19, 36, 0.6)",
    "glow": "#cfd8f5",
}
# unabhängig von hell und dunkel
FIXED: dict[str, str] = {
    "white": "#fff",  # reines Weiß und Schwarz: Aufhellen und Abdunkeln in color-mix
    "black": "#000",
    "radius": "6px",
    "radius-sm": "4px",
    "radius-xs": "2px",
    "font-heading": "'Unbounded Variable', Unbounded, system-ui, sans-serif",
    "font-sans": "'IBM Plex Sans', system-ui, -apple-system, 'Segoe UI', sans-serif",
    "font-mono": "'IBM Plex Mono', ui-monospace, monospace",
    "ease": "cubic-bezier(0.2, 0.8, 0.2, 1)",
}
# Was beide Oberflächen gleich zeichnen: die Glaskarte, der Hintergrund und der sichtbare Tastaturfokus
RULES = """\
/* Hintergrund: ein ruhiger Schein von unten, keine Bewegung */
.backdrop {
	position: fixed;
	inset: 0;
	z-index: -1;
	background: radial-gradient(1200px 800px at 50% 120%, var(--glow), transparent 70%), var(--bg);
}

/* Glaskarte: durchscheinend mit feiner Kante und Lichtkante oben */
.glass {
	position: relative;
	background: var(--glass);
	border: 1px solid var(--edge-soft);
	border-radius: var(--radius);
	box-shadow: inset 0 1px 0 var(--glass-shine);
	backdrop-filter: blur(var(--glass-blur)) saturate(1.3);
	-webkit-backdrop-filter: blur(var(--glass-blur)) saturate(1.3);
}

:focus-visible {
	outline: 2px solid var(--accent);
	outline-offset: 2px;
}

/* Akkordeon (<details class="fold">): Die Überschrift bleibt stehen, ein Klick zeigt den Inhalt darunter */
details.fold > summary {
	display: flex;
	align-items: center;
	gap: 12px;
	cursor: pointer;
	list-style: none;
}
details.fold > summary::-webkit-details-marker {
	display: none;
}
details.fold > summary::after {
	content: "";
	flex-shrink: 0;
	width: 8px;
	height: 8px;
	margin: 0 4px 4px auto;
	border-right: 2px solid var(--dim);
	border-bottom: 2px solid var(--dim);
	transform: rotate(45deg);
	transition: transform 0.15s var(--ease);
}
details.fold[open] > summary::after {
	margin-bottom: -4px;
	transform: rotate(-135deg);
}
details.fold > summary:hover::after {
	border-color: var(--text);
}

@media (prefers-reduced-motion: reduce) {
	*,
	*::before,
	*::after {
		animation-duration: 0.01ms !important;
		transition-duration: 0.01ms !important;
		scroll-behavior: auto !important;
	}
}
"""


def _block(selector: str, values: dict[str, str], scheme: str = "") -> str:
    lines = [f"\t--{name}: {value};" for name, value in values.items()]
    if scheme:
        lines.append(f"\tcolor-scheme: {scheme};")
    return f"{selector} {{\n" + "\n".join(lines) + "\n}\n"


def tokens_css(header: str) -> str:
    return "\n".join([f"/* {header} Quelle: proto/nexproto/design.py */",
                      _block(":root", {**DARK, **FIXED}, "dark"),
                      _block(':root[data-theme="light"]', LIGHT, "light"), RULES])
