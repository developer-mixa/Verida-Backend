from __future__ import annotations

from typing import Annotated

from fastapi import Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.features.articles.repositories.article_repository import ArticleRepository
from app.features.articles.repositories.article_study_repository import ArticleStudyRepository


def get_article_repository(db: Annotated[AsyncSession, Depends(get_db)]) -> ArticleRepository:
    return ArticleRepository(db)


def get_article_study_repository(db: Annotated[AsyncSession, Depends(get_db)]) -> ArticleStudyRepository:
    return ArticleStudyRepository(db)
