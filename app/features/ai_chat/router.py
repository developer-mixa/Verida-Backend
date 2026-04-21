from __future__ import annotations

import json
from collections.abc import AsyncIterator
from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.responses import StreamingResponse
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import AsyncSessionLocal, get_db
from app.core.deps import get_current_user_id
from app.features.ai_chat.deps import get_chat_llm, get_chat_repository
from app.features.ai_chat.llm.openai_chat_llm import OpenAiChatLlm
from app.features.ai_chat.repositories.chat_repository import ChatRepository
from app.features.ai_chat.schemas import (
    ChatMessageIn,
    ChatSessionCreate,
    ChatSessionOut,
    ChatSynopsisRequest,
    ChatSynopsisResponse,
    SynopsisTagOut,
)

router = APIRouter(prefix="/chat", tags=["ai"])


@router.post(
    "/sessions",
    response_model=ChatSessionOut,
    status_code=status.HTTP_201_CREATED,
    summary="Создать тему чата",
    description="Новая тема = отдельный контекст. Требуется JWT.",
)
async def create_chat_session(
    payload: ChatSessionCreate,
    user_id: Annotated[UUID, Depends(get_current_user_id)],
    db: Annotated[AsyncSession, Depends(get_db)],
    repo: Annotated[ChatRepository, Depends(get_chat_repository)],
) -> ChatSessionOut:
    row = await repo.create_session(user_id=user_id, title=payload.title)
    await db.commit()
    await db.refresh(row)
    return ChatSessionOut.model_validate(row)


@router.post(
    "/sessions/{session_id}/messages/stream",
    summary="Отправить сообщение; ответ ассистента — SSE",
    description=(
        "Поток `text/event-stream`: события JSON в `data:` (`session`, `delta`, `error`, `done`). "
        "Требуется JWT. Сообщение пользователя и ответ ассистента сохраняются в БД."
    ),
)
async def stream_chat_message(
    session_id: UUID,
    payload: ChatMessageIn,
    user_id: Annotated[UUID, Depends(get_current_user_id)],
    db: Annotated[AsyncSession, Depends(get_db)],
    llm: Annotated[OpenAiChatLlm, Depends(get_chat_llm)],
    repo: Annotated[ChatRepository, Depends(get_chat_repository)],
) -> StreamingResponse:
    sess = await repo.get_session_owned(session_id=session_id, user_id=user_id)
    if sess is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Сессия не найдена")

    await repo.add_message(session_id=session_id, role="user", content=payload.content)
    await db.commit()

    async def event_stream() -> AsyncIterator[bytes]:
        yield _sse({"event": "session", "session_id": str(session_id)})
        async with AsyncSessionLocal() as read_session:
            read_repo = ChatRepository(read_session)
            messages = await read_repo.list_messages_for_llm(session_id=session_id)
        accumulated: list[str] = []
        try:
            async for piece in llm.stream_reply(messages=messages):
                accumulated.append(piece)
                yield _sse({"event": "delta", "text": piece})
        except RuntimeError as exc:
            yield _sse({"event": "error", "message": str(exc)})
            return
        assistant_text = "".join(accumulated)
        async with AsyncSessionLocal() as write_session:
            write_repo = ChatRepository(write_session)
            await write_repo.add_message(
                session_id=session_id,
                role="assistant",
                content=assistant_text,
            )
            await write_session.commit()
        yield _sse({"event": "done"})

    return StreamingResponse(
        event_stream(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )


def _sse(obj: object) -> bytes:
    line = "data: " + json.dumps(obj, ensure_ascii=False) + "\n\n"
    return line.encode("utf-8")


@router.post(
    "/sessions/{session_id}/synopsis",
    response_model=ChatSynopsisResponse,
    summary="Конспект по текущему диалогу",
    description=(
        "Статья-конспект в БД только здесь (не при обычном чате). "
        "Function calling `save_synopsis` → upsert `articles` для темы. Требуется JWT."
    ),
    responses={
        404: {"description": "Сессия не найдена"},
        422: {"description": "Нет сообщений в теме"},
        502: {"description": "Ошибка вызова LLM"},
    },
)
async def create_synopsis_from_session(
    session_id: UUID,
    payload: ChatSynopsisRequest,
    user_id: Annotated[UUID, Depends(get_current_user_id)],
    db: Annotated[AsyncSession, Depends(get_db)],
    llm: Annotated[OpenAiChatLlm, Depends(get_chat_llm)],
    repo: Annotated[ChatRepository, Depends(get_chat_repository)],
) -> ChatSynopsisResponse:
    sess = await repo.get_session_owned(session_id=session_id, user_id=user_id)
    if sess is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Сессия не найдена")

    messages = await repo.list_messages_for_llm(session_id=session_id)
    if not messages:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="В теме нет сообщений для конспекта",
        )
    dialogue_block = "\n".join(f"{m['role']}: {m['content']}" for m in messages)
    try:
        args = await llm.synopsis_save_args(
            dialogue_block=dialogue_block,
            language=payload.language,
        )
    except RuntimeError as exc:
        raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail=str(exc)) from exc

    raw_tags = args.get("tags") or []
    if not isinstance(raw_tags, list):
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail="Некорректный формат tags от LLM",
        )
    tag_pairs: list[tuple[str, str]] = []
    for item in raw_tags:
        if not isinstance(item, dict):
            continue
        at = str(item.get("article_type", "")).strip()
        an = str(item.get("article_name", "")).strip()
        if at and an:
            tag_pairs.append((at, an))
    if not tag_pairs:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail="Нет валидных тегов в ответе LLM",
        )

    article, updated = await repo.upsert_synopsis_article(
        session=sess,
        user_id=user_id,
        title=str(args["title"]),
        content=str(args["content"]),
        tag_pairs=tag_pairs,
    )
    await db.commit()
    await db.refresh(article, attribute_names=["tags"])
    return ChatSynopsisResponse(
        article_id=article.id,
        updated=updated,
        title=article.title,
        tags=[SynopsisTagOut.model_validate(t) for t in article.tags],
    )
