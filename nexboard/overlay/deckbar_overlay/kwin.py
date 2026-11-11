"""KWin: Fensterregeln für Meter- und Plugin-Fenster, Hauptmonitor laut KDE."""
from __future__ import annotations

import json
import shutil
import subprocess

from PySide6.QtCore import QSettings

from .const import APP, MAIN_TITLE, PLUGIN_TITLE


def ensure_kwin_rule() -> None:
    """Legacy: Meter-Fenster über dem Vollbild-Spiel per KWin-Regel Ebene „Overlay“ (wie beim
    A2Tools-Meter). Nur einmal je Fenstertitel anlegen; was der Nutzer danach ändert, bleibt so."""
    store = QSettings("deckbar", "overlay")
    if store.value("kwinRuleTitle") == MAIN_TITLE or not shutil.which("kwriteconfig6"):
        return
    group = "deckbar-overlay"

    def kw(key: str, value: str, grp: str = group) -> None:
        subprocess.run(["kwriteconfig6", "--file", "kwinrulesrc", "--group", grp, "--key", key, value], check=False)

    rules = subprocess.run(["kreadconfig6", "--file", "kwinrulesrc", "--group", "General", "--key", "rules"],
                           capture_output=True, text=True).stdout.strip()
    names = [r for r in rules.split(",") if r]
    kw("Description", "NexBoard DPS-Meter über dem Spiel")
    kw("title", MAIN_TITLE)
    kw("titlematch", "1")  # exakt
    kw("wmclass", APP)  # WM_CLASS ist "deckbar-overlay", "deckbar-overlay" (-name + Programmname)
    kw("wmclasscomplete", "true")
    kw("wmclassmatch", "2")  # enthält
    kw("layer", "overlay")
    kw("layerrule", "2")  # erzwingen
    if group not in names:
        names.append(group)
        kw("rules", ",".join(names), "General")
        kw("count", str(len(names)), "General")
    subprocess.run(["qdbus6", "org.kde.KWin", "/KWin", "reconfigure"], check=False, capture_output=True)
    store.setValue("kwinRuleTitle", MAIN_TITLE)  # neuer Titel (Umbenennung) → Regel wird nachgezogen


def ensure_plugin_kwin_rule() -> None:
    """Plugin-Fenster über dem Spiel halten (Qt kann das unter Wayland nicht selbst). Nur einmal
    anlegen; was der Nutzer danach ändert, bleibt so."""
    store = QSettings("deckbar", "overlay")
    if store.value("kwinPluginRule") or not shutil.which("kwriteconfig6"):
        return
    group = "deckbar-plugins"

    def kw(key: str, value: str, grp: str = group) -> None:
        subprocess.run(["kwriteconfig6", "--file", "kwinrulesrc", "--group", grp, "--key", key, value], check=False)

    rules = subprocess.run(["kreadconfig6", "--file", "kwinrulesrc", "--group", "General", "--key", "rules"],
                           capture_output=True, text=True).stdout.strip()
    names = [r for r in rules.split(",") if r]
    kw("Description", "NexBoard Plugin-Fenster über dem Spiel")
    kw("title", PLUGIN_TITLE)
    kw("titlematch", "2")  # enthält
    kw("wmclass", APP)
    kw("wmclasscomplete", "true")
    kw("wmclassmatch", "2")
    kw("layer", "overlay")
    kw("layerrule", "2")
    if group not in names:
        names.append(group)
        kw("rules", ",".join(names), "General")
        kw("count", str(len(names)), "General")
    subprocess.run(["qdbus6", "org.kde.KWin", "/KWin", "reconfigure"], check=False, capture_output=True)
    store.setValue("kwinPluginRule", True)


def kde_primary() -> str:
    """Hauptmonitor laut KDE (Priorität 1). Qt meldet unter Wayland oft einfach den ersten Ausgang."""
    if not shutil.which("kscreen-doctor"):
        return ""
    try:
        out = subprocess.run(["kscreen-doctor", "-j"], capture_output=True, text=True, timeout=3).stdout
        outputs = [o for o in json.loads(out).get("outputs", []) if o.get("enabled")]
        best = min(outputs, key=lambda o: o.get("priority") or 99)
        return str(best.get("name") or "")
    except (OSError, ValueError, subprocess.SubprocessError, AttributeError):
        return ""
