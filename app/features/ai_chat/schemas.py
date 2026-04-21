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
    model_config = {"from_attributes": True}

    id: UUID
    title: str
    created_at: datetime


class ChatMessageIn(BaseModel):
    """Одно сообщение пользователя в рамках темы."""

    content: str = Field(..., min_length=1, max_length=32_000)


class ChatSynopsisRequest(BaseModel):
    """Параметры генерации конспекта по текущему диалогу (расширится под LLM)."""

    language: str | None = Field(default="ru", max_length=10)


class SynopsisTagOut(BaseModel):
    """Тег статьи после конспекта (article_type задаёт модель на английском)."""

    model_config = {"from_attributes": True}

    id: UUID
    article_type: str = Field(max_length=128)
    article_name: str = Field(max_length=255)


class ChatSynopsisResponse(BaseModel):
    """Ответ после сохранения конспекта в `articles`."""

    article_id: UUID
    updated: bool = Field(description="true если обновлена существующая статья темы")
    title: str
    tags: list[SynopsisTagOut] = Field(default_factory=list)
