"""Discord-OAuth2: Code gegen Token tauschen, Konto und Server-Rollen lesen."""
from __future__ import annotations

from dataclasses import dataclass
from urllib.parse import urlencode

import httpx

from .config import Settings

API = "https://discord.com/api/v10"
AUTHORIZE = "https://discord.com/oauth2/authorize"


class DiscordError(Exception):
    """Discord hat nicht oder unerwartet geantwortet."""


@dataclass(frozen=True)
class DiscordUser:
    id: int
    username: str
    global_name: str | None
    avatar: str | None


class Discord:
    def __init__(self, settings: Settings, http: httpx.AsyncClient) -> None:
        self.settings = settings
        self.http = http

    def scopes(self) -> list[str]:
        # Server-Rollen nur abfragen, wenn eine Mitgliedsrolle festgelegt ist
        return ["identify", "guilds.members.read"] if self.settings.member_check else ["identify"]

    def authorize_url(self, state: str, code_challenge: str) -> str:
        params = {
            "client_id": self.settings.discord_client_id,
            "redirect_uri": self.settings.redirect_uri,
            "response_type": "code",
            "scope": " ".join(self.scopes()),
            "state": state,
            "code_challenge": code_challenge,
            "code_challenge_method": "S256",
            "prompt": "none",
        }
        return f"{AUTHORIZE}?{urlencode(params)}"

    async def exchange_code(self, code: str, code_verifier: str) -> str:
        data = {
            "grant_type": "authorization_code",
            "code": code,
            "redirect_uri": self.settings.redirect_uri,
            "code_verifier": code_verifier,
        }
        r = await self._request("POST", "/oauth2/token", data=data, auth=self._client_auth())
        if r.status_code != 200:
            raise DiscordError(f"Token-Tausch fehlgeschlagen: HTTP {r.status_code}")
        return r.json()["access_token"]

    async def get_user(self, token: str) -> DiscordUser:
        r = await self._request("GET", "/users/@me", headers=_bearer(token))
        if r.status_code != 200:
            raise DiscordError(f"Konto nicht lesbar: HTTP {r.status_code}")
        u = r.json()
        return DiscordUser(int(u["id"]), u["username"], u.get("global_name"), u.get("avatar"))

    async def get_member_roles(self, token: str, guild_id: int) -> set[int] | None:
        """Rollen des Kontos auf dem Server; None, wenn es dort kein Mitglied ist."""
        r = await self._request("GET", f"/users/@me/guilds/{guild_id}/member", headers=_bearer(token))
        if r.status_code == 404:
            return None
        if r.status_code != 200:
            raise DiscordError(f"Server-Mitgliedschaft nicht lesbar: HTTP {r.status_code}")
        return {int(x) for x in r.json().get("roles", [])}

    async def revoke(self, token: str) -> None:
        """Token sofort zurückgeben; der Hub braucht ihn nach dem Login nicht mehr."""
        try:
            await self._request("POST", "/oauth2/token/revoke",
                                data={"token": token, "token_type_hint": "access_token"},
                                auth=self._client_auth())
        except DiscordError:
            pass

    def _client_auth(self) -> httpx.BasicAuth:
        return httpx.BasicAuth(self.settings.discord_client_id, self.settings.discord_client_secret)

    async def _request(self, method: str, path: str, **kw) -> httpx.Response:
        try:
            return await self.http.request(method, API + path, **kw)
        except httpx.HTTPError as e:
            raise DiscordError(f"Discord nicht erreichbar: {e!r}") from e


def _bearer(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}
