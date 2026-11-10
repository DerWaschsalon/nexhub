"""Module des Bots, je Bereich ein Ordner (Konzept „TheWashBot – Umbau auf kleine Module“).

MODULES ist die Liste, die der Host lädt; ein neues Modul kommt hier dazu, der Kern bleibt gleich.
"""
from .community.bump import Bump
from .server.announcements import Announcements
from .server.counters import Counters
from .server.custom_commands import CustomCommands
from .server.embeds import Embeds
from .server.roles import Roles
from .server.tempvoice import TempVoice
from .server.welcome import Welcome

MODULES = (Welcome, Roles, TempVoice, Counters, Announcements, CustomCommands, Embeds, Bump)

__all__ = ["MODULES"]
