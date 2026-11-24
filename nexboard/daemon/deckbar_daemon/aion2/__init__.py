"""AION 2 jenseits der DPS-Kette: Welt, Cubes, Gruppe, Feldbosse, Warnungen und Ansagen.

Alles hier hängt an der Paketquelle (core.packets) und bekommt dekodierte Nachrichten. `World` hält, was
mehrere brauchen (eigene ID, Position, Zone, Namen, Bosse); die Tracker halten je ein Thema und melden über
Signale, was passiert ist.
"""
