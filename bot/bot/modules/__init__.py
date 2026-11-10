"""Module des Bots, je Bereich ein Ordner (Konzept „TheWashBot – Umbau auf kleine Module“).

MODULES ist die Liste, die der Host lädt; ein neues Modul kommt hier dazu, der Kern bleibt gleich.
"""
from .community.bump import Bump

MODULES = (Bump,)

__all__ = ["MODULES"]
