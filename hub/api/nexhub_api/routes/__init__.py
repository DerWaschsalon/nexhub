"""Alle Bereiche der API. Ein neuer Bereich = eine Datei hier mit `router` + Eintrag in ROUTERS.

Konvention für Pfade:
    /api/public/…  ohne Login (öffentlicher Bereich)
    /api/…         mit Login (CurrentUser), /api/admin/… nur Admins
"""
from . import account, admin, armory, auth, bis, bot, characters, devices, poe, public, runs

ROUTERS = [auth.router, account.router, devices.router, runs.router, characters.router, armory.router,
           bis.router, public.router, admin.router, bot.router,
           poe.router, poe.internal]
