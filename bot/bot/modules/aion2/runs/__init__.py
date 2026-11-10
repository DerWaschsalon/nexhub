"""Runs aus dem NexBoard: Post je Dungeon-Run (posts.py), Bilder (image.py), Bestzeiten und Rekorde
(records.py), Anzeige (format.py), /aion und /dungeon-rangliste (commands.py). Ein Modul, weil der Post
die Rekorde braucht, bevor er rausgeht."""
from .posts import RunPosts

__all__ = ["RunPosts"]
