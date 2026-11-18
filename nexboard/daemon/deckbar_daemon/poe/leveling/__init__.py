"""Leveling-Guide für PoE 1 nach dem Act Tracker von Exile-UI (github.com/Lailloken/Exile-UI, MIT).

Die Regeln (welcher Schritt, welche Gems als Belohnung, wann es weitergeht) sind die des Originals,
damit sich der Guide genauso verhält. Daten und Bilder in data/ stammen von dort (LICENSE-Exile-UI.md).

    data.py        Zonen, Gems, Quests
    pob.py         Path-of-Building-Code lesen
    guide.py       Seiten des Guides bauen (Gems aus dem Build als Belohnung/Kauf einsetzen)
    tracker.py     wo man im Guide steht, vor/zurück, automatisch weiter beim Betreten der Zielzone
    markup.py      Zeilen einer Seite in farbige Stücke zerlegen
    experience.py  XP-Abzug nach Stufenabstand
    leveling.py    alles zusammen, mit Speicher und Anzeige
"""
