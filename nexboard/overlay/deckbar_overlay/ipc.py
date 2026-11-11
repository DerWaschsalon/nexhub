"""Befehle an die laufende Instanz: ein Socket im Laufzeitordner."""
from __future__ import annotations

from PySide6.QtNetwork import QLocalSocket

from .daemon_client import socket_path


def send_to_running(cmd: str) -> bool:
    sock = QLocalSocket()
    sock.connectToServer(socket_path())
    if not sock.waitForConnected(500):
        return False
    sock.write(cmd.encode() + b"\n")
    sock.waitForBytesWritten(500)
    sock.disconnectFromServer()
    return True
