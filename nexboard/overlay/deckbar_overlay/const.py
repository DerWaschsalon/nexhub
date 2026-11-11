"""Namen, Befehle und Pfade des Overlay-Programms: die eine Quelle dafür."""
from pathlib import Path

APP = "deckbar-overlay"
PLUGIN_TITLE = " (Plugin)"  # Fenstertitel, an ihm hängt die KWin-Regel
MAIN_TITLE = "NexBoard DPS-Meter"  # KWin-Regel (nur Legacy): Ebene „Overlay“ für dieses Fenster
REPO = Path(__file__).resolve().parents[2]
HERE = Path(__file__).resolve().parents[1]  # overlay/: Overlay.qml, focus.js
ICON = REPO / "capture" / "a2tools" / "src-tauri" / "icons" / "128x128.png"
COMMANDS = ("toggle", "show", "hide", "edit", "lock", "click", "reload", "details", "history", "settings", "quit",
            "autohide-on", "autohide-off")
MODES = ("click", "lock", "edit")
# Fokus: AION 2 unter Steam/Proton hat die Fensterklasse steam_app_3393110 (Titel „AION2“).
# Nur über die Klasse bzw. den exakten Titel: Browser-Tabs mit „AION2“ im Titel zählen nicht.
GAME_CLASS = "steam_app_3393110"
GAME_TITLE = "AION2"
FOCUS_SCRIPT = "deckbar-overlay-focus"  # Name des KWin-Skripts (focus.js)
FOCUS_DBUS = "org.deckbar.Overlay"
FOCUS_HIDE_MS = 150  # kurz warten: beim Fensterwechsel ist zwischendurch oft gar nichts aktiv
TOOL_SIZES = {"settings": (760, 820, 520, 420), "history": (1100, 720, 480, 360), "details": (1180, 760, 520, 360)}
