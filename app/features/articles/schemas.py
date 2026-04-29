from __future__ import annotations

from datetime import datetime
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
    parent_id: UUID | None
    is_folder: bool
    tags: list[ArticleTagOut] = Field(default_factory=list)


class ArticleDetailOut(BaseModel):
    model_config = {"from_attributes": True}

    id: UUID
    title: str
    content: str
    chat_session_id: UUID | None
    parent_id: UUID | None
    is_folder: bool
    tags: list[ArticleTagOut] = Field(default_factory=list)


class ArticleTagIn(BaseModel):
    article_type: str = Field(min_length=1, max_length=128)
    article_name: str = Field(min_length=1, max_length=255)


class ArticleCreateIn(BaseModel):
    title: str = Field(min_length=1, max_length=500)
    content: str = Field(default="")
    tags: list[ArticleTagIn] = Field(default_factory=list)
    chat_session_id: UUID | None = None
    parent_id: UUID | None = None
    is_folder: bool = False

    @model_validator(mode="after")
    def content_required_for_notes(self) -> ArticleCreateIn:
        if not self.is_folder and (not self.content or not self.content.strip()):
            raise ValueError("Для заметки укажите непустой content")
        return self


class ArticleUpdateIn(BaseModel):
    title: str | None = Field(default=None, min_length=1, max_length=500)
    content: str | None = Field(default=None, min_length=1)
    tags: list[ArticleTagIn] | None = None
    parent_id: UUID | None = None
    is_folder: bool | None = None

    @model_validator(mode="after")
    def at_least_one_field(self) -> ArticleUpdateIn:
        if not self.model_fields_set:
            raise ValueError("Укажите хотя бы одно поле для обновления")
        return self


class ArticleQuestionOut(BaseModel):
    model_config = {"from_attributes": True}

    id: UUID
    question: str
    answer: str


class ArticleQuestionCreateIn(BaseModel):
    question: str = Field(min_length=1)
    answer: str = Field(min_length=1)


class ArticleQuestionUpdateIn(BaseModel):
    question: str | None = Field(default=None, min_length=1)
    answer: str | None = Field(default=None, min_length=1)

    @model_validator(mode="after")
    def at_least_one_field(self) -> ArticleQuestionUpdateIn:
        if self.question is None and self.answer is None:
            raise ValueError("Укажите хотя бы одно из полей: question, answer")
        return self


class ArticleStudySessionOut(BaseModel):
    id: UUID
    user_id: UUID
    article_id: UUID
    deck_order: list[UUID]
    total_cards: int
    correct_count: int
    created_at: datetime
    completed_at: datetime | None


class ArticleStudyReviewIn(BaseModel):
    question_id: UUID
    is_correct: bool


class ArticleStudyReviewResultOut(BaseModel):
    correct_count: int
    total_cards: int
    reviews_submitted: int
    session_completed: bool


class ArticleImportZipOut(BaseModel):
    created_count: int
    root_article_ids: list[UUID]
