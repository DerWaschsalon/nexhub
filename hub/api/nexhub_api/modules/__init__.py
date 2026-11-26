"""Die Module der Hub-API. Ein neues Modul = ein Ordner hier mit `MODULE` und eine Zeile in MODULES.

Konvention für Pfade:
    /api/public/…  ohne Login (öffentlicher Bereich)
    /api/…         mit Login (CurrentUser), /api/admin/… nur Admins
"""
from ..module import ApiModule
from . import armory, bis, bot, devices, feedback, logs, loot, parses, schedule, stats

# Reihenfolge wie im Web (lib/modules.ts); die Routen des Kerns stehen in routes/
MODULES: tuple[ApiModule, ...] = (logs.MODULE, armory.MODULE, bis.MODULE, loot.MODULE, parses.MODULE,
                                  schedule.MODULE, devices.MODULE, feedback.MODULE, bot.MODULE, stats.MODULE)
