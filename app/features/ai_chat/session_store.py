"""Временное хранилище сессий без БД. Заменить на таблицы SQLAlchemy."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from uuid import UUID, uuid4

from app.features.ai_chat.schemas import ChatSessionOut


@dataclass
class _Session:
    id: UUID
    title: str
    created_at: datetime


_SESSIONS: dict[UUID, _Session] = {}


def create_session(*, title: str | None) -> ChatSessionOut:
    sid = uuid4()
    resolved_title = (title or "").strip() or "Новая тема"
    row = _Session(id=sid, title=resolved_title, created_at=datetime.now(timezone.utc))
    _SESSIONS[sid] = row
    return ChatSessionOut(id=row.id, title=row.title, created_at=row.created_at)


def get_session(session_id: UUID) -> _Session | None:
    return _SESSIONS.get(session_id)
