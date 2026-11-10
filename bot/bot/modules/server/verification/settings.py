"""Zustand der Verifizierung: kein Formular, eingerichtet wird über /setup verifizierung oder das Panel."""

from pydantic import BaseModel


class VerificationSettings(BaseModel):
    verify_active: bool = False
    verify_role: int | None = None
    verify_channel: int | None = None
    verify_message: int | None = None  # Regeln-Panel mit dem Knopf „Regeln akzeptiert“
