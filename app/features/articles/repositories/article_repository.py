from __future__ import annotations

import uuid

from sqlalchemy import delete, select, update
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.core.models.article import Article
from app.core.models.chat_session import ChatSession
from app.features.articles.tag_sync import get_or_create_tags, sync_article_tags


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

    async def _session_owned(self, *, session_id: uuid.UUID, user_id: uuid.UUID) -> ChatSession | None:
        r = await self._db.execute(
            select(ChatSession).where(ChatSession.id == session_id, ChatSession.user_id == user_id)
        )
        return r.scalar_one_or_none()

    async def create(
        self,
        *,
        user_id: uuid.UUID,
        title: str,
        content: str,
        tag_pairs: list[tuple[str, str]],
        chat_session_id: uuid.UUID | None,
    ) -> Article:
        if chat_session_id is not None:
            sess = await self._session_owned(session_id=chat_session_id, user_id=user_id)
            if sess is None:
                raise ValueError("chat_session_not_found")

        article = Article(
            user_id=user_id,
            chat_session_id=chat_session_id,
            title=title[:500],
            content=content,
        )
        self._db.add(article)
        await self._db.flush()
        tags = await get_or_create_tags(self._db, tag_pairs)
        await sync_article_tags(self._db, article_id=article.id, tags=tags)
        r2 = await self._db.execute(
            select(Article)
            .where(Article.id == article.id)
            .options(selectinload(Article.tags))
            .execution_options(populate_existing=True)
        )
        return r2.scalar_one()

    async def update_owned(
        self,
        *,
        article_id: uuid.UUID,
        user_id: uuid.UUID,
        title: str | None,
        content: str | None,
        tag_pairs: list[tuple[str, str]] | None,
    ) -> Article | None:
        row = await self.get_owned(article_id=article_id, user_id=user_id)
        if row is None:
            return None
        if title is not None:
            row.title = title[:500]
        if content is not None:
            row.content = content
        if tag_pairs is not None:
            tags = await get_or_create_tags(self._db, tag_pairs)
            await sync_article_tags(self._db, article_id=row.id, tags=tags)
        await self._db.flush()
        r2 = await self._db.execute(
            select(Article)
            .where(Article.id == row.id)
            .options(selectinload(Article.tags))
            .execution_options(populate_existing=True)
        )
        return r2.scalar_one()

    async def delete_owned(self, *, article_id: uuid.UUID, user_id: uuid.UUID) -> bool:
        row = await self.get_owned(article_id=article_id, user_id=user_id)
        if row is None:
            return False
        await self._db.execute(
            update(ChatSession)
            .where(ChatSession.active_article_id == article_id)
            .values(active_article_id=None)
        )
        await self._db.execute(delete(Article).where(Article.id == article_id, Article.user_id == user_id))
        await self._db.flush()
        return True
