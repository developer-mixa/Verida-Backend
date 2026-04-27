from __future__ import annotations

import uuid
from datetime import datetime
from typing import TYPE_CHECKING

from sqlalchemy import Boolean, DateTime, ForeignKey, UniqueConstraint, Uuid, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base

if TYPE_CHECKING:
    from app.core.models.article_question import ArticleQuestion
    from app.core.models.article_study_session import ArticleStudySession


class ArticleQuestionReview(Base):
    """Ответ пользователя на карточку в рамках сессии (для веса и статистики)."""

    __tablename__ = "article_question_reviews"
    __table_args__ = (
        UniqueConstraint(
            "study_session_id",
            "question_id",
            name="uq_article_question_reviews_session_question",
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
    )
    question_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("article_questions.id", ondelete="CASCADE"),
        nullable=False,
    )
    study_session_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("article_study_sessions.id", ondelete="CASCADE"),
        nullable=False,
    )
    is_correct: Mapped[bool] = mapped_column(Boolean, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
    )

    question: Mapped[ArticleQuestion] = relationship("ArticleQuestion", back_populates="reviews")
    study_session: Mapped[ArticleStudySession] = relationship(
        "ArticleStudySession",
        back_populates="reviews",
    )
