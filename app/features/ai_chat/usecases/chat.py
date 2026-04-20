"""Сценарий «сообщение в чат»; вызов репозитория LLM — позже."""

from __future__ import annotations

from collections.abc import AsyncIterator

from app.features.ai_chat.ports.ai_chat_repository import ChatAiRepository


class ChatUsecase:
    def __init__(self, chat_repository: ChatAiRepository) -> None:
        self._repo = chat_repository

    def stream_reply(self, *, message: str) -> AsyncIterator[str]:
        """Заготовка: должен проксировать поток из репозитория."""
        return self._repo.msg_to_chat(
            model="",
            instructions="",
            input_text=message,
            previous_response_id=None,
        )
