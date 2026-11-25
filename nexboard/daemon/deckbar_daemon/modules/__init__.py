"""Module des Daemons: je eine Klasse, die eine Komponente mit Routen, Status und Lebenszyklus in die
Registry von nexcore hängt. Die Komponenten selbst werden mit ihrem Bereich neu gebaut (Schritte 6–9)."""

# Bereiche der Web-UI: je Spiel einer, dazu Leiste, NexHub und System (ModuleInfo.category). Die Seitenleiste
# zeigt einen Bereich mit mehreren Seiten als aufklappbare Gruppe.
CATEGORIES = {
    "aion2": "AION 2",
    "poe1": "Path of Exile",
    "bar": "Touch-Leiste",
    "share": "NexHub",
    "system": "System",
}
