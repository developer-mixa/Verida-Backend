from __future__ import annotations

import uuid

from sqlalchemy import Column, ForeignKey, PrimaryKeyConstraint, String, Table, Uuid
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base


article_tags = Table(
    "article_tags",
    Base.metadata,
    Column("article_id", Uuid(as_uuid=True), ForeignKey("articles.id", ondelete="CASCADE"), nullable=False),
    Column("tag_id", Uuid(as_uuid=True), ForeignKey("tags.id", ondelete="CASCADE"), nullable=False),
    PrimaryKeyConstraint("article_id", "tag_id", name="pk_article_tags"),
)


class Tag(Base):
    __tablename__ = "tags"

    id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid.uuid4)
    article_type: Mapped[str] = mapped_column(String(128), nullable=False)
    article_name: Mapped[str] = mapped_column(String(255), nullable=False)

    articles: Mapped[list[Article]] = relationship(secondary=article_tags, back_populates="tags")
