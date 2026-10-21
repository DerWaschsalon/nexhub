"""Alle Bereiche der API. Ein neuer Bereich = eine Datei hier mit `router` + Eintrag in ROUTERS.

Konvention für Pfade:
    /api/public/…  ohne Login (öffentlicher Bereich)
    /api/…         mit Login (CurrentUser), /api/admin/… nur Admins
"""
from . import account, admin, auth, devices, public

ROUTERS = [auth.router, account.router, devices.router, public.router, admin.router]
