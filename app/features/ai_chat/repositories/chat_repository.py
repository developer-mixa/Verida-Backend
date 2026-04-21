from __future__ import annotations

import uuid
from datetime import datetime, timezone

from sqlalchemy import delete, func, insert, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.models.article import Article
from app.core.models.chat_message import ChatMessage
from app.core.models.chat_session import ChatSession
from app.core.models.tag import Tag, article_tags


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

    async def _get_or_create_tags(self, pairs: list[tuple[str, str]]) -> list[Tag]:
        """Пары (article_type, article_name): дедупликация, поиск по lower(article_type)+article_name."""
        if not pairs:
            return []
        out: list[Tag] = []
        seen: set[tuple[str, str]] = set()
        for raw_type, raw_name in pairs:
            article_type = (raw_type or "").strip()[:128]
            article_name = (raw_name or "").strip()[:255]
            if not article_type or not article_name:
                continue
            key = (article_type.lower(), article_name)
            if key in seen:
                continue
            seen.add(key)
            r = await self._db.execute(
                select(Tag).where(
                    func.lower(Tag.article_type) == article_type.lower(),
                    Tag.article_name == article_name,
                )
            )
            row = r.scalar_one_or_none()
            if row is None:
                row = Tag(article_type=article_type, article_name=article_name)
                self._db.add(row)
                await self._db.flush()
            out.append(row)
        return out

    async def _sync_article_tags(self, *, article_id: uuid.UUID, tags: list[Tag]) -> None:
        """Перезапись связей M2M без lazy-load коллекции (async-safe)."""
        await self._db.execute(delete(article_tags).where(article_tags.c.article_id == article_id))
        for t in tags:
            await self._db.execute(
                insert(article_tags).values(article_id=article_id, tag_id=t.id),
            )
        await self._db.flush()

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
        tags = await self._get_or_create_tags(tag_pairs)
        if existing is not None:
            existing.title = title[:500]
            existing.content = content
            session.active_article_id = existing.id
            await self._db.flush()
            await self._sync_article_tags(article_id=existing.id, tags=tags)
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
        await self._sync_article_tags(article_id=article.id, tags=tags)
        await self._db.refresh(article)
        session.active_article_id = article.id
        await self._db.flush()
        return article, False
