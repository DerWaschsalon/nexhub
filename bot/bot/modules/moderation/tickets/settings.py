"""Einstellungen der Tickets."""

from pydantic import BaseModel

from bot.core import IdList
from bot.core.schema import setting


class TicketSettings(BaseModel):
    ticket_team_roles: IdList = setting("roles", "Team-Rollen", [])
