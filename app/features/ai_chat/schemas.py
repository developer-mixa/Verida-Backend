from __future__ import annotations

from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, Field


class ChatSessionCreate(BaseModel):
    """Создание новой темы (отдельный контекст)."""

    title: str | None = Field(
        default=None,
        max_length=200,
        description="Заголовок темы; если не задан — будет дефолтный",
    )


class ChatSessionOut(BaseModel):
    id: UUID
    title: str
    created_at: datetime


class ChatMessageIn(BaseModel):
    """Одно сообщение пользователя в рамках темы."""

    content: str = Field(..., min_length=1, max_length=32_000)


class ChatSynopsisRequest(BaseModel):
    """Параметры генерации конспекта по текущему диалогу (расширится под LLM)."""

    language: str | None = Field(default="ru", max_length=10)


class ChatSynopsisOut(BaseModel):
    id: UUID
    session_id: UUID
    status: str = Field(description="например: pending | ready")
    created_at: datetime
