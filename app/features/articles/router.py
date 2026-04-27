from __future__ import annotations

from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.ext.asyncio import AsyncSession
from starlette.responses import Response

from app.core.database import get_db
from app.core.deps import get_current_user_id
from app.core.models.article_study_session import ArticleStudySession
from app.features.articles.deps import get_article_repository, get_article_study_repository
from app.features.articles.repositories.article_repository import ArticleRepository
from app.features.articles.repositories.article_study_repository import ArticleStudyRepository
from app.features.articles.schemas import (
    ArticleCreateIn,
    ArticleDetailOut,
    ArticleQuestionCreateIn,
    ArticleQuestionOut,
    ArticleQuestionUpdateIn,
    ArticleStudyReviewIn,
    ArticleStudyReviewResultOut,
    ArticleStudySessionOut,
    ArticleSummaryOut,
    ArticleUpdateIn,
)

router = APIRouter(prefix="/articles", tags=["articles"])


def _study_session_out(row: ArticleStudySession) -> ArticleStudySessionOut:
    return ArticleStudySessionOut(
        id=row.id,
        user_id=row.user_id,
        article_id=row.article_id,
        deck_order=[UUID(x) for x in row.deck_order],
        total_cards=row.total_cards,
        correct_count=row.correct_count,
        created_at=row.created_at,
        completed_at=row.completed_at,
    )


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
    "/{article_id}/questions",
    response_model=list[ArticleQuestionOut],
    summary="Карточки вопрос–ответ по статье",
    description="Список пар вопрос/ответ для самопроверки. Только своя статья.",
)
async def list_article_questions(
    article_id: UUID,
    user_id: Annotated[UUID, Depends(get_current_user_id)],
    study_repo: Annotated[ArticleStudyRepository, Depends(get_article_study_repository)],
) -> list[ArticleQuestionOut]:
    rows = await study_repo.list_questions(article_id=article_id, user_id=user_id)
    if rows is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Статья не найдена")
    return [ArticleQuestionOut.model_validate(q) for q in rows]


@router.post(
    "/{article_id}/questions",
    response_model=ArticleQuestionOut,
    status_code=status.HTTP_201_CREATED,
    summary="Добавить карточку",
    description="Ручное создание пары вопрос/ответ. Только своя статья.",
)
async def create_article_question(
    article_id: UUID,
    payload: ArticleQuestionCreateIn,
    user_id: Annotated[UUID, Depends(get_current_user_id)],
    db: Annotated[AsyncSession, Depends(get_db)],
    study_repo: Annotated[ArticleStudyRepository, Depends(get_article_study_repository)],
) -> ArticleQuestionOut:
    row = await study_repo.create_question(
        article_id=article_id,
        user_id=user_id,
        question=payload.question.strip(),
        answer=payload.answer.strip(),
    )
    if row is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Статья не найдена")
    await db.commit()
    return ArticleQuestionOut.model_validate(row)


@router.patch(
    "/{article_id}/questions/{question_id}",
    response_model=ArticleQuestionOut,
    summary="Обновить карточку",
    description="Частичное обновление вопроса и/или ответа. Только своя статья.",
)
async def update_article_question(
    article_id: UUID,
    question_id: UUID,
    payload: ArticleQuestionUpdateIn,
    user_id: Annotated[UUID, Depends(get_current_user_id)],
    db: Annotated[AsyncSession, Depends(get_db)],
    study_repo: Annotated[ArticleStudyRepository, Depends(get_article_study_repository)],
) -> ArticleQuestionOut:
    row = await study_repo.update_question(
        article_id=article_id,
        user_id=user_id,
        question_id=question_id,
        question=payload.question.strip() if payload.question is not None else None,
        answer=payload.answer.strip() if payload.answer is not None else None,
    )
    if row is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Карточка не найдена")
    await db.commit()
    return ArticleQuestionOut.model_validate(row)


@router.delete(
    "/{article_id}/questions/{question_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Удалить карточку",
    description="Удаление пары вопрос/ответ. Только своя статья.",
    response_class=Response,
)
async def delete_article_question(
    article_id: UUID,
    question_id: UUID,
    user_id: Annotated[UUID, Depends(get_current_user_id)],
    db: Annotated[AsyncSession, Depends(get_db)],
    study_repo: Annotated[ArticleStudyRepository, Depends(get_article_study_repository)],
) -> Response:
    ok = await study_repo.delete_question(
        article_id=article_id, user_id=user_id, question_id=question_id
    )
    if not ok:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Карточка не найдена")
    await db.commit()
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.post(
    "/{article_id}/study-sessions",
    response_model=ArticleStudySessionOut,
    status_code=status.HTTP_201_CREATED,
    summary="Начать сессию вопрос–ответ",
    description="Создаёт проход по всем карточкам статьи; порядок с учётом истории неверных ответов.",
)
async def start_article_study_session(
    article_id: UUID,
    user_id: Annotated[UUID, Depends(get_current_user_id)],
    db: Annotated[AsyncSession, Depends(get_db)],
    study_repo: Annotated[ArticleStudyRepository, Depends(get_article_study_repository)],
) -> ArticleStudySessionOut:
    started = await study_repo.start_study_session(article_id=article_id, user_id=user_id)
    if started == "not_owned":
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Статья не найдена")
    if started == "empty":
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Нет карточек для тренировки",
        )
    await db.commit()
    return _study_session_out(started)


@router.get(
    "/{article_id}/study-sessions/{session_id}",
    response_model=ArticleStudySessionOut,
    summary="Состояние сессии",
    description="Порядок колоды, счётчик верных и признак завершения. Только своя сессия по статье.",
)
async def get_article_study_session(
    article_id: UUID,
    session_id: UUID,
    user_id: Annotated[UUID, Depends(get_current_user_id)],
    study_repo: Annotated[ArticleStudyRepository, Depends(get_article_study_repository)],
) -> ArticleStudySessionOut:
    row = await study_repo.get_study_session(
        article_id=article_id, user_id=user_id, session_id=session_id
    )
    if row is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Сессия не найдена")
    return _study_session_out(row)


@router.post(
    "/{article_id}/study-sessions/{session_id}/reviews",
    response_model=ArticleStudyReviewResultOut,
    summary="Зафиксировать самооценку по карточке",
    description="Одна запись на карточку за сессию. После последней карточки сессия помечается завершённой.",
)
async def submit_article_study_review(
    article_id: UUID,
    session_id: UUID,
    payload: ArticleStudyReviewIn,
    user_id: Annotated[UUID, Depends(get_current_user_id)],
    db: Annotated[AsyncSession, Depends(get_db)],
    study_repo: Annotated[ArticleStudyRepository, Depends(get_article_study_repository)],
) -> ArticleStudyReviewResultOut:
    result = await study_repo.submit_study_review(
        article_id=article_id,
        user_id=user_id,
        session_id=session_id,
        question_id=payload.question_id,
        is_correct=payload.is_correct,
    )
    if result == "session_not_found":
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Сессия не найдена")
    if result == "already_completed":
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Сессия уже завершена")
    if result == "bad_question":
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Карточка не входит в эту сессию",
        )
    if result == "duplicate":
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Ответ по этой карточке в сессии уже записан",
        )
    await db.commit()
    return ArticleStudyReviewResultOut(
        correct_count=result.correct_count,
        total_cards=result.total_cards,
        reviews_submitted=result.reviews_submitted,
        session_completed=result.session_completed,
    )


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
