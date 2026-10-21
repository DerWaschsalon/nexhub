"""Einstellungen aus Umgebungsvariablen (auf dem Server: /srv/nexhub/.env)."""
from __future__ import annotations

from pathlib import Path
from typing import Annotated
from urllib.parse import urlsplit

from pydantic import field_validator
from pydantic_settings import BaseSettings, NoDecode, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(extra="ignore")

    database_url: str = "postgresql+asyncpg://nexhub@localhost/nexhub"
    # Adresse, unter der Browser den Hub aufrufen; daraus entsteht die Redirect-URL für Discord.
    # Ohne Domain per SSH-Tunnel: http://localhost:8080
    hub_base_url: str = "http://localhost:8080"
    # Signiert den kurzlebigen OAuth-Cookie. Ändern meldet nur laufende Logins ab, keine Sitzungen.
    hub_secret_key: str
    discord_client_id: str = ""
    discord_client_secret: str = ""
    # Discord-IDs mit Admin-Rolle, kommagetrennt
    hub_admin_ids: Annotated[frozenset[int], NoDecode] = frozenset()
    # Mitglied ist, wer auf diesem Discord-Server diese Rolle hat. Leer: nur Admins kommen rein.
    hub_guild_id: int | None = None
    hub_member_role_id: int | None = None
    hub_session_days: int = 30
    # Gebaute Web-Oberfläche (hub/web/build); leer: nur die API
    hub_web_dir: Path | None = None
    # Stand des Codes, setzt das Image beim Bauen (z. B. "monorepo@71b65a2")
    hub_version: str = "dev"
    # Hochgeladene Dateien (runs/<id>.nexlog.gz); im Container ein eigenes Volume
    hub_data_dir: Path = Path("data")
    # Steuer-API von TheWashBot im internen Docker-Netz (z. B. http://bot:8790) und ihr Schlüssel
    # (BOT_CONTROL_KEY, auf beiden Seiten gleich). Leer: der Bereich „Bot“ meldet „nicht verbunden“.
    bot_control_url: str = ""
    bot_control_key: str = ""
    # Anbieterkennzeichnung für /impressum und /datenschutz – öffentlich sichtbar, steht nur in .env,
    # nie im Repo. Anschrift: Zeilen mit „;“ getrennt. Leer: die Seiten sagen „noch nicht eingetragen“.
    hub_operator_name: str = ""
    hub_operator_address: str = ""
    hub_operator_email: str = ""
    # Wo der Server läuft (Anbieter, Land), für die Datenschutzerklärung; leer: allgemeiner Satz
    hub_hoster: str = ""

    @field_validator("hub_admin_ids", mode="before")
    @classmethod
    def _split_ids(cls, v: object) -> object:
        if isinstance(v, str):
            return frozenset(int(x) for x in v.replace(" ", "").split(",") if x)
        return v

    @field_validator("hub_guild_id", "hub_member_role_id", "hub_web_dir", mode="before")
    @classmethod
    def _empty_is_none(cls, v: object) -> object:
        return None if v == "" else v

    @field_validator("hub_base_url", "bot_control_url")
    @classmethod
    def _strip_slash(cls, v: str) -> str:
        return v.rstrip("/")

    @property
    def origin(self) -> str:
        u = urlsplit(self.hub_base_url)
        return f"{u.scheme}://{u.netloc}"

    @property
    def secure_cookies(self) -> bool:
        return self.hub_base_url.startswith("https://")

    @property
    def redirect_uri(self) -> str:
        return f"{self.hub_base_url}/api/auth/callback"

    @property
    def operator(self) -> dict | None:
        if not self.hub_operator_name.strip():
            return None
        return {"name": self.hub_operator_name.strip(),
                "address": [line.strip() for line in self.hub_operator_address.split(";") if line.strip()],
                "email": self.hub_operator_email.strip() or None}

    @property
    def discord_configured(self) -> bool:
        return bool(self.discord_client_id and self.discord_client_secret)

    @property
    def bot_configured(self) -> bool:
        return bool(self.bot_control_url and self.bot_control_key)

    @property
    def member_check(self) -> bool:
        return self.hub_guild_id is not None and self.hub_member_role_id is not None
