from __future__ import annotations

from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.ext.asyncio import AsyncSession
from starlette.responses import Response

from app.core.database import get_db
from app.core.deps import get_current_user_id
from app.features.articles.deps import get_article_repository
from app.features.articles.repositories.article_repository import ArticleRepository
from app.features.articles.schemas import (
    ArticleCreateIn,
    ArticleDetailOut,
    ArticleSummaryOut,
    ArticleUpdateIn,
)

router = APIRouter(prefix="/articles", tags=["articles"])


@router.get(
    "",
    response_model=list[ArticleSummaryOut],
    summary="Список статей пользователя",
    description="Статьи текущего пользователя (в т.ч. конспекты из чатов), с тегами. Требуется JWT.",
)
async def list_my_articles(
    user_id: Annotated[UUID, Depends(get_current_user_id)],
    repo: Annotated[ArticleRepository, Depends(get_article_repository)],
    limit: int = Query(default=50, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
) -> list[ArticleSummaryOut]:
    rows = await repo.list_for_user(user_id=user_id, limit=limit, offset=offset)
    return [ArticleSummaryOut.model_validate(a) for a in rows]


@router.get(
    "/{article_id}",
    response_model=ArticleDetailOut,
    summary="Детали статьи",
    description="Полный текст и теги; только своя статья. Требуется JWT.",
    responses={404: {"description": "Статья не найдена"}},
)
async def get_article_detail(
    article_id: UUID,
    user_id: Annotated[UUID, Depends(get_current_user_id)],
    repo: Annotated[ArticleRepository, Depends(get_article_repository)],
) -> ArticleDetailOut:
    row = await repo.get_owned(article_id=article_id, user_id=user_id)
    if row is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Статья не найдена")
    return ArticleDetailOut.model_validate(row)


@router.post(
    "",
    response_model=ArticleDetailOut,
    status_code=status.HTTP_201_CREATED,
    summary="Создать статью или конспект",
    description="Ручное создание заметки (без LLM). Опционально привязать к своей теме чата. Требуется JWT.",
)
async def create_article(
    payload: ArticleCreateIn,
    user_id: Annotated[UUID, Depends(get_current_user_id)],
    db: Annotated[AsyncSession, Depends(get_db)],
    repo: Annotated[ArticleRepository, Depends(get_article_repository)],
) -> ArticleDetailOut:
    pairs = [(t.article_type, t.article_name) for t in payload.tags]
    try:
        row = await repo.create(
            user_id=user_id,
            title=payload.title.strip(),
            content=payload.content,
            tag_pairs=pairs,
            chat_session_id=payload.chat_session_id,
        )
    except ValueError as e:
        if str(e) == "chat_session_not_found":
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Тема чата не найдена или не принадлежит вам",
            ) from e
        raise
    await db.commit()
    r = await repo.get_owned(article_id=row.id, user_id=user_id)
    assert r is not None
    return ArticleDetailOut.model_validate(r)


@router.patch(
    "/{article_id}",
    response_model=ArticleDetailOut,
    summary="Обновить статью",
    description="Частичное обновление title, content и/или tags. Только своя статья. Требуется JWT.",
)
async def update_article(
    article_id: UUID,
    payload: ArticleUpdateIn,
    user_id: Annotated[UUID, Depends(get_current_user_id)],
    db: Annotated[AsyncSession, Depends(get_db)],
    repo: Annotated[ArticleRepository, Depends(get_article_repository)],
) -> ArticleDetailOut:
    pairs: list[tuple[str, str]] | None = None
    if payload.tags is not None:
        pairs = [(t.article_type, t.article_name) for t in payload.tags]
    row = await repo.update_owned(
        article_id=article_id,
        user_id=user_id,
        title=payload.title.strip() if payload.title is not None else None,
        content=payload.content if payload.content is not None else None,
        tag_pairs=pairs,
    )
    if row is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Статья не найдена")
    await db.commit()
    r = await repo.get_owned(article_id=article_id, user_id=user_id)
    assert r is not None
    return ArticleDetailOut.model_validate(r)


@router.delete(
    "/{article_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Удалить статью",
    description="Удаление своей статьи и связей с тегами. Требуется JWT.",
    response_class=Response,
)
async def delete_article(
    article_id: UUID,
    user_id: Annotated[UUID, Depends(get_current_user_id)],
    db: Annotated[AsyncSession, Depends(get_db)],
    repo: Annotated[ArticleRepository, Depends(get_article_repository)],
) -> Response:
    ok = await repo.delete_owned(article_id=article_id, user_id=user_id)
    if not ok:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Статья не найдена")
    await db.commit()
    return Response(status_code=status.HTTP_204_NO_CONTENT)
