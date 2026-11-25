"""Feedback-Board: Mitglieder schreiben Wünsche und stimmen ab, Admins setzen den Status.

    GET    /api/feedback                 alle Einträge mit Stimmenzahl und der eigenen Stimme
    POST   /api/feedback                 neuer Eintrag (höchstens PER_DAY je Konto und Tag)
    POST   /api/feedback/{id}/vote       Stimme geben
    DELETE /api/feedback/{id}/vote       Stimme zurücknehmen
    PUT    /api/admin/feedback/{id}      Status setzen (nur Admins)
    DELETE /api/admin/feedback/{id}      löschen (nur Admins)

Für andere Mitglieder sind Einträge anonym; den Namen sehen nur Admins.
"""
from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import Literal

from fastapi import APIRouter, HTTPException, Response
from pydantic import BaseModel, Field
from sqlalchemy import delete, func, select

from ..db import aware
from ..deps import DB, AdminUser, CurrentUser
from ..models import Feedback, FeedbackVote, User

router = APIRouter(tags=["feedback"])

PER_DAY = 5
Status = Literal["neu", "gesehen", "geplant", "erledigt", "abgelehnt"]


class FeedbackEntry(BaseModel):
    id: int
    title: str
    body: str
    status: Status
    created_at: datetime
    votes: int
    voted: bool  # hat dieses Konto schon gestimmt?
    mine: bool
    author: str | None  # nur für Admins


class NewEntry(BaseModel):
    title: str = Field(min_length=3, max_length=120)
    body: str = Field("", max_length=2000)


class NewStatus(BaseModel):
    status: Status


async def _entry(db: DB, row: Feedback, user: User) -> FeedbackEntry:
    votes = await db.scalar(select(func.count()).select_from(FeedbackVote).where(FeedbackVote.feedback_id == row.id))
    voted = await db.get(FeedbackVote, (row.id, user.id)) is not None
    author = (await db.get(User, row.user_id)).name if user.role == "admin" else None
    return FeedbackEntry(id=row.id, title=row.title, body=row.body, status=row.status, created_at=aware(row.created_at),
                 votes=votes or 0, voted=voted, mine=row.user_id == user.id, author=author)


async def _get(db: DB, feedback_id: int) -> Feedback:
    row = await db.get(Feedback, feedback_id)
    if row is None:
        raise HTTPException(404, "Eintrag nicht gefunden")
    return row


@router.get("/api/feedback")
async def list_feedback(user: CurrentUser, db: DB) -> list[FeedbackEntry]:
    """Die meisten Stimmen zuerst, bei Gleichstand der neuere."""
    rows = (await db.scalars(select(Feedback).order_by(Feedback.created_at.desc()))).all()
    entries = [await _entry(db, row, user) for row in rows]
    return sorted(entries, key=lambda e: -e.votes)


@router.post("/api/feedback", status_code=201)
async def add_feedback(body: NewEntry, user: CurrentUser, db: DB) -> FeedbackEntry:
    since = datetime.now(UTC) - timedelta(days=1)
    today = await db.scalar(select(func.count()).select_from(Feedback).where(
        Feedback.user_id == user.id, Feedback.created_at >= since))
    if (today or 0) >= PER_DAY:
        raise HTTPException(429, f"Höchstens {PER_DAY} Einträge am Tag")
    row = Feedback(user_id=user.id, title=body.title.strip(), body=body.body.strip(), status="neu")
    db.add(row)
    await db.flush()
    db.add(FeedbackVote(feedback_id=row.id, user_id=user.id))  # der eigene Wunsch zählt als erste Stimme
    await db.commit()
    await db.refresh(row)
    return await _entry(db, row, user)


@router.post("/api/feedback/{feedback_id}/vote")
async def vote(feedback_id: int, user: CurrentUser, db: DB) -> FeedbackEntry:
    row = await _get(db, feedback_id)
    if await db.get(FeedbackVote, (row.id, user.id)) is None:
        db.add(FeedbackVote(feedback_id=row.id, user_id=user.id))
        await db.commit()
    return await _entry(db, row, user)


@router.delete("/api/feedback/{feedback_id}/vote")
async def unvote(feedback_id: int, user: CurrentUser, db: DB) -> FeedbackEntry:
    row = await _get(db, feedback_id)
    mine = (FeedbackVote.feedback_id == row.id, FeedbackVote.user_id == user.id)
    await db.execute(delete(FeedbackVote).where(*mine))
    await db.commit()
    return await _entry(db, row, user)


@router.put("/api/admin/feedback/{feedback_id}")
async def set_status(feedback_id: int, body: NewStatus, admin: AdminUser, db: DB) -> FeedbackEntry:
    row = await _get(db, feedback_id)
    row.status, row.updated_at = body.status, datetime.now(UTC)
    await db.commit()
    await db.refresh(row)
    return await _entry(db, row, admin)


@router.delete("/api/admin/feedback/{feedback_id}", status_code=204)
async def remove(feedback_id: int, admin: AdminUser, db: DB) -> Response:
    row = await _get(db, feedback_id)
    # ausdrücklich, weil SQLite (Tests) ON DELETE CASCADE ohne PRAGMA foreign_keys nicht ausführt
    await db.execute(delete(FeedbackVote).where(FeedbackVote.feedback_id == row.id))
    await db.delete(row)
    await db.commit()
    return Response(status_code=204)
