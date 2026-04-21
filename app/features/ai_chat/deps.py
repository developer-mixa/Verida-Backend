from __future__ import annotations

from typing import Annotated

from fastapi import Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from fastapi import HTTPException, status

from app.features.ai_chat.llm.openai_chat_llm import OpenAiChatLlm
from app.features.ai_chat.repositories.chat_repository import ChatRepository


def get_chat_repository(db: Annotated[AsyncSession, Depends(get_db)]) -> ChatRepository:
    return ChatRepository(db)


def get_chat_llm() -> OpenAiChatLlm:
    try:
        return OpenAiChatLlm()
    except RuntimeError as exc:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=str(exc),
        ) from exc
