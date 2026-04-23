from __future__ import annotations

from uuid import UUID

from pydantic import BaseModel, Field, model_validator


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


class ArticleTagIn(BaseModel):
    article_type: str = Field(min_length=1, max_length=128)
    article_name: str = Field(min_length=1, max_length=255)


class ArticleCreateIn(BaseModel):
    title: str = Field(min_length=1, max_length=500)
    content: str = Field(min_length=1)
    tags: list[ArticleTagIn] = Field(default_factory=list)
    chat_session_id: UUID | None = None


class ArticleUpdateIn(BaseModel):
    title: str | None = Field(default=None, min_length=1, max_length=500)
    content: str | None = Field(default=None, min_length=1)
    tags: list[ArticleTagIn] | None = None

    @model_validator(mode="after")
    def at_least_one_field(self) -> ArticleUpdateIn:
        if self.title is None and self.content is None and self.tags is None:
            raise ValueError("Укажите хотя бы одно из полей: title, content, tags")
        return self
