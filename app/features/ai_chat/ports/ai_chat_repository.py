from __future__ import annotations

from collections.abc import AsyncIterator, Mapping, Sequence
from typing import Any, Optional, Protocol

from openai import OpenAI

class ChatAiRepository(Protocol):
    """Порт к LLM (Yandex и т.д.); реализация подключится позже."""

    client: OpenAI

    def msg_to_chat(
        self,
        *,
        model: str,
        instructions: str,
        input_text: str,
        previous_response_id: Optional[str],
        store: bool = True,
        tools: Optional[Sequence[Mapping[str, Any]]] = None,
    ) -> AsyncIterator[str]:
        """Поток текстовых чанков ответа ассистента."""
