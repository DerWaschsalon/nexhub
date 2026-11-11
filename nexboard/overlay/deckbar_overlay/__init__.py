"""NexBoard-Overlay (Paket; Starter: overlay/deckbar-overlay): Meter und Widgets über dem Spiel, mit Tray-Symbol.

Unter KDE Plasma (Wayland) legt das Programm eine durchsichtige layer-shell-Fläche über den
Spielmonitor (Ebene „overlay“, über dem Vollbildspiel) und zeigt darin die Widget-Seite des
Daemons (daemon/deckbar_daemon/web/overlay/): das A2Tools-Meter, Boss-Leiste, Event-Timer,
Name mit Effekt. Die Fläche bekommt nie die Tastatur (außer beim Bearbeiten) und nimmt Klicks
nur dort an, wo es nötig ist:

    click   (Standard) nur das Meter nimmt Klicks an, alles andere geht ans Spiel
    lock    nur noch der Schloss-Knopf des Meters (wie die Sperre im A2Tools-Meter)
    edit    alles: Widgets ziehen, Mausrad = Größe, Esc = fertig

Unter KWin blendet sich die Fläche aus, solange ein anderes Fenster als AION 2 den Fokus hat
(Einstellung hide_unfocused, KWin-Skript focus.js meldet jeden Fensterwechsel per D-Bus).

    deckbar-overlay                 starten (Tray)
    deckbar-overlay --toggle        Overlay zeigen/verbergen (für ein Tastenkürzel)
    deckbar-overlay --edit          Bearbeiten an/aus
    deckbar-overlay --lock | --click | --show | --hide | --reload
    deckbar-overlay --details | --history | --settings | --quit
    deckbar-overlay --autohide-on | --autohide-off   nur bei aktivem Spiel zeigen an/aus
    deckbar-overlay --profile NAME  Overlay-Profil wählen (welche Widgets sichtbar sind)
    deckbar-overlay --widget ID     ein Widget ein-/ausblenden (meter, boss, timers, cube, map, warnings)
    deckbar-overlay --legacy        altes Meter-Fenster unter XWayland (ohne Widgets)

Ein zweiter Aufruf gibt den Befehl an die laufende Instanz weiter (Socket im Laufzeitordner,
auch der Daemon schickt darüber Befehle aus der Web-UI). Details, Verlauf und Einstellungen des
Meters sind normale Fenster. Ohne layer-shell (GNOME, X11, layer-shell-qt fehlt) läuft
automatisch das alte Meter-Fenster unter XWayland mit KWin-Regel und Input-Shape.

Braucht PySide6 mit QtWebEngine, für layer-shell zusätzlich layer-shell-qt
(pacman -S pyside6 qt6-webengine layer-shell-qt).
"""
