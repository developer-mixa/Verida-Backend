from __future__ import annotations

import uuid

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.core.models.article import Article


class ArticleRepository:
    def __init__(self, db: AsyncSession) -> None:
        self._db = db

    async def list_for_user(
        self,
        *,
        user_id: uuid.UUID,
        limit: int = 100,
        offset: int = 0,
    ) -> list[Article]:
        r = await self._db.execute(
            select(Article)
            .where(Article.user_id == user_id)
            .options(selectinload(Article.tags))
            .order_by(Article.id.desc())
            .offset(offset)
            .limit(min(limit, 200))
        )
        return list(r.scalars().unique().all())

    async def get_owned(self, *, article_id: uuid.UUID, user_id: uuid.UUID) -> Article | None:
        r = await self._db.execute(
            select(Article)
            .where(Article.id == article_id, Article.user_id == user_id)
            .options(selectinload(Article.tags))
        )
        return r.scalar_one_or_none()
