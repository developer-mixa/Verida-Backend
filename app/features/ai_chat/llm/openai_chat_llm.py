from __future__ import annotations

import os
from collections.abc import AsyncIterator

from openai import AsyncOpenAI

from app.features.ai_chat.llm.chat_stream import iter_chat_reply
from app.features.ai_chat.llm.synopsis_response_parse import (
    _save_synopsis_arguments_from_response,
    parse_synopsis_from_response,
)
from app.features.ai_chat.llm.synopsis_runner import run_synopsis_save_args

# Реэкспорт для тестов (tests/features/ai_chat/test_synopsis_response_parse.py).
__all__ = [
    "OpenAiChatLlm",
    "_save_synopsis_arguments_from_response",
    "parse_synopsis_from_response",
]


class OpenAiChatLlm:
    """Клиент AsyncOpenAI под Yandex (переменные окружения как в AI Studio / cloud)."""

    def __init__(self) -> None:
        api_key = os.getenv("YANDEX_GPT_API_KEY") or ""
        folder_id = os.getenv("YANDEX_GPT_FOLDER_ID") or ""
        base_url = os.getenv("YANDEX_GPT_BASE_URL") or None
        self._model = (os.getenv("YANDEX_GPT_MODEL") or "").strip()
        if not api_key or not self._model:
            raise RuntimeError("YANDEX_GPT_API_KEY и YANDEX_GPT_MODEL должны быть заданы в окружении")
        self._client = AsyncOpenAI(
            api_key=api_key,
            base_url=base_url,
            project=folder_id or None,
        )

    @property
    def configured(self) -> bool:
        return bool((os.getenv("YANDEX_GPT_API_KEY") or "").strip() and (os.getenv("YANDEX_GPT_MODEL") or "").strip())

    async def stream_reply(self, *, messages: list[dict[str, str]]) -> AsyncIterator[str]:
        async for chunk in iter_chat_reply(self._client, self._model, messages=messages):
            yield chunk

    async def synopsis_save_args(
        self, *, dialogue_block: str, language: str | None
    ) -> dict[str, str | list[dict[str, str]]]:
        return await run_synopsis_save_args(
            self._client,
            self._model,
            dialogue_block=dialogue_block,
            language=language,
        )
