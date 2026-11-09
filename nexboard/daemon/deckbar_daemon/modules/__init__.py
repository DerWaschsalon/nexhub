"""Module des Daemons: je eine Klasse, die eine Komponente mit Routen, Status und Lebenszyklus in die
Registry von nexcore hängt. Die Komponenten selbst werden mit ihrem Bereich neu gebaut (Schritte 6–9)."""

# Bereiche der Web-UI: nach Situation, nicht nach Technik (ModuleInfo.category)
CATEGORIES = {
    "ingame": "Im Spiel",
    "bar": "Leiste",
    "share": "Teilen",
    "system": "System",
}
