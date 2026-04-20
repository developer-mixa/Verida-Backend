from __future__ import annotations

import json
from collections.abc import AsyncIterator
from uuid import UUID

from fastapi import APIRouter, HTTPException, status
from fastapi.responses import StreamingResponse

from app.features.ai_chat.schemas import (
    ChatMessageIn,
    ChatSessionCreate,
    ChatSessionOut,
    ChatSynopsisRequest,
)
from app.features.ai_chat.session_store import create_session, get_session

router = APIRouter(prefix="/chat", tags=["ai"])


@router.post(
    "/sessions",
    response_model=ChatSessionOut,
    status_code=status.HTTP_201_CREATED,
    summary="Создать тему чата",
    description="Новая тема = отдельный контекст (сообщения привяжутся к session_id после появления БД).",
)
async def create_chat_session(payload: ChatSessionCreate) -> ChatSessionOut:
    return create_session(title=payload.title)


@router.post(
    "/sessions/{session_id}/messages/stream",
    summary="Отправить сообщение; ответ ассистента — SSE",
    description=(
        "Поток `text/event-stream`: события JSON в `data:`. "
        "Сейчас заглушка; позже — проксирование стрима Yandex."
    ),
)
async def stream_chat_message(session_id: UUID, payload: ChatMessageIn) -> StreamingResponse:
    if get_session(session_id) is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Сессия не найдена")

    async def event_stream() -> AsyncIterator[bytes]:
        yield _sse({"event": "session", "session_id": str(session_id)})
        stub = "Заглушка: здесь будет поток ответа модели."
        for word in stub.split():
            yield _sse({"event": "delta", "text": word + " "})
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
    summary="Конспект по текущему диалогу",
    description="Сохранение структурированного конспекта в БД (function calling) — в разработке.",
    responses={
        404: {"description": "Сессия не найдена"},
        501: {"description": "Конспект и БД ещё не подключены"},
    },
)
async def create_synopsis_from_session(
    session_id: UUID,
    _payload: ChatSynopsisRequest,
) -> None:
    if get_session(session_id) is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Сессия не найдена")
    raise HTTPException(
        status_code=status.HTTP_501_NOT_IMPLEMENTED,
        detail="Конспект и БД ещё не подключены.",
    )
