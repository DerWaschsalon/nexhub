"""Tabellen des Moduls Feedback. Änderungen immer mit Alembic-Migration."""
from __future__ import annotations

from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, String, func
from sqlalchemy.orm import Mapped, mapped_column

from ...models import Base, BigID


class Feedback(Base):
    """Ein Wunsch oder Hinweis eines Mitglieds. Wer ihn schrieb, sehen nur Admins."""

    __tablename__ = "feedback"

    id: Mapped[int] = mapped_column(BigID, primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    title: Mapped[str] = mapped_column(String(120))
    body: Mapped[str] = mapped_column(String(2000), server_default="")
    status: Mapped[str] = mapped_column(String(16), server_default="neu")  # siehe modules/feedback/routes.py STATUSES
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class FeedbackVote(Base):
    """Eine Stimme für einen Wunsch; je Konto höchstens eine."""

    __tablename__ = "feedback_votes"

    feedback_id: Mapped[int] = mapped_column(ForeignKey("feedback.id", ondelete="CASCADE"), primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), primary_key=True)
