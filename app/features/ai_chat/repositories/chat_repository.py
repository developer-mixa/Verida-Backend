from __future__ import annotations

import uuid
from datetime import datetime, timezone

from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.models.article import Article
from app.core.models.chat_message import ChatMessage
from app.core.models.chat_session import ChatSession
from app.features.articles.tag_sync import get_or_create_tags, sync_article_tags


class ChatRepository:
    def __init__(self, db: AsyncSession) -> None:
        self._db = db

    async def create_session(self, *, user_id: uuid.UUID, title: str | None) -> ChatSession:
        resolved = (title or "").strip() or "Новая тема"
        row = ChatSession(user_id=user_id, title=resolved[:200])
        self._db.add(row)
        await self._db.flush()
        await self._db.refresh(row)
        return row

    async def get_session_owned(self, *, session_id: uuid.UUID, user_id: uuid.UUID) -> ChatSession | None:
        r = await self._db.execute(
            select(ChatSession).where(
                ChatSession.id == session_id,
                ChatSession.user_id == user_id,
            )
        )
        return r.scalar_one_or_none()

    async def list_messages_for_llm(
        self,
        *,
        session_id: uuid.UUID,
        limit: int = 80,
    ) -> list[dict[str, str]]:
        r = await self._db.execute(
            select(ChatMessage)
            .where(ChatMessage.session_id == session_id)
            .order_by(ChatMessage.created_at.asc())
            .limit(limit)
        )
        rows = list(r.scalars().all())
        return [{"role": m.role, "content": m.content} for m in rows]

    async def add_message(
        self,
        *,
        session_id: uuid.UUID,
        role: str,
        content: str,
        payload: dict | list | None = None,
    ) -> ChatMessage:
        msg = ChatMessage(session_id=session_id, role=role, content=content, payload=payload)
        self._db.add(msg)
        await self._db.execute(
            update(ChatSession)
            .where(ChatSession.id == session_id)
            .values(updated_at=datetime.now(timezone.utc))
        )
        await self._db.flush()
        await self._db.refresh(msg)
        return msg

    async def upsert_synopsis_article(
        self,
        *,
        session: ChatSession,
        user_id: uuid.UUID,
        title: str,
        content: str,
        tag_pairs: list[tuple[str, str]],
    ) -> tuple[Article, bool]:
        r = await self._db.execute(
            select(Article)
            .where(Article.chat_session_id == session.id)
            .order_by(Article.id.asc())
            .limit(1)
        )
        existing = r.scalar_one_or_none()
        tags = await get_or_create_tags(self._db, tag_pairs)
        if existing is not None:
            existing.title = title[:500]
            existing.content = content
            session.active_article_id = existing.id
            await self._db.flush()
            await sync_article_tags(self._db, article_id=existing.id, tags=tags)
            await self._db.refresh(existing)
            return existing, True

        article = Article(
            user_id=user_id,
            chat_session_id=session.id,
            title=title[:500],
            content=content,
        )
        self._db.add(article)
        await self._db.flush()
        await sync_article_tags(self._db, article_id=article.id, tags=tags)
        await self._db.refresh(article)
        session.active_article_id = article.id
        await self._db.flush()
        return article, False
