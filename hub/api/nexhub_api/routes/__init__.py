"""Routen des Kerns: Anmeldung, eigenes Konto, Verwaltung der Konten, öffentliche Angaben zum Hub.
Alles andere gehört zu einem Modul (modules/<id>/)."""
from . import account, admin, auth, public

ROUTERS = (auth.router, account.router, public.router, admin.router)
