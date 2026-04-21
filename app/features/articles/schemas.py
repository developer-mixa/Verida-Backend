from __future__ import annotations

from uuid import UUID

from pydantic import BaseModel, Field


class ArticleTagOut(BaseModel):
    model_config = {"from_attributes": True}

    id: UUID
    article_type: str = Field(max_length=128)
    article_name: str = Field(max_length=255)


class ArticleSummaryOut(BaseModel):
    model_config = {"from_attributes": True}

    id: UUID
    title: str
    chat_session_id: UUID | None
    tags: list[ArticleTagOut] = Field(default_factory=list)


class ArticleDetailOut(BaseModel):
    model_config = {"from_attributes": True}

    id: UUID
    title: str
    content: str
    chat_session_id: UUID | None
    tags: list[ArticleTagOut] = Field(default_factory=list)
