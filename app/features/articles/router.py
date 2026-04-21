from __future__ import annotations

from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, status

from app.core.deps import get_current_user_id
from app.features.articles.deps import get_article_repository
from app.features.articles.repositories.article_repository import ArticleRepository
from app.features.articles.schemas import ArticleDetailOut, ArticleSummaryOut

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
