"""Werkzeuge mit eigener Logik: Dungeons, die A2Tools nur als Nummer kennt, bekommen ihren Namen über ihre Bosse."""
from deckbar_daemon.aion2.gamedata import ZONES

from werkzeuge.bosse import dungeons_ueber_bosse


def test_neue_dungeons_ueber_ihre_bosse():
    assert ZONES[600082] == "Abyssal Forge: Ludra"
    npcs = {"1": {"name": "Eternal Ludra", "isBoss": True, "dungeonId": 600082},
            "2": {"name": "Kromede's Desire", "isBoss": True, "dungeonId": 200003},  # Albtraum: viele
            "3": {"name": "Sura", "isBoss": True, "dungeonId": 200003},  # Bosse, nur einer
            "4": {"name": "Zikel", "isBoss": True, "dungeonId": 200003}}  # bekannt
    assert dungeons_ueber_bosse(npcs, {}) == {"600082": "Abyssal Forge: Ludra"}
