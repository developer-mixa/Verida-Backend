"""Общая логика M2M тегов для статей (конспектов)."""

from __future__ import annotations

import uuid

from sqlalchemy import delete, func, insert, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.models.tag import Tag, article_tags


async def get_or_create_tags(db: AsyncSession, pairs: list[tuple[str, str]]) -> list[Tag]:
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
        r = await db.execute(
            select(Tag).where(
                func.lower(Tag.article_type) == article_type.lower(),
                Tag.article_name == article_name,
            )
        )
        row = r.scalar_one_or_none()
        if row is None:
            row = Tag(article_type=article_type, article_name=article_name)
            db.add(row)
            await db.flush()
        out.append(row)
    return out


async def sync_article_tags(db: AsyncSession, *, article_id: uuid.UUID, tags: list[Tag]) -> None:
    """Перезапись связей M2M без lazy-load коллекции (async-safe)."""
    await db.execute(delete(article_tags).where(article_tags.c.article_id == article_id))
    for t in tags:
        await db.execute(insert(article_tags).values(article_id=article_id, tag_id=t.id))
    await db.flush()
