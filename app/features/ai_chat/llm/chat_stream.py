from __future__ import annotations

from collections.abc import AsyncIterator

from openai import APIError, AsyncOpenAI
from openai.types.responses import (
    ResponseErrorEvent,
    ResponseFailedEvent,
    ResponseTextDeltaEvent,
)

from app.features.ai_chat.llm.chat_system import SYSTEM_CHAT
from app.features.ai_chat.llm.dialogue_limits import (
    dialog_to_responses_input,
    max_tool_calls_responses,
    trim_messages_for_responses,
)
from app.features.ai_chat.llm.yandex_web_search_tools import yandex_responses_web_search_tools


async def iter_chat_reply(
    client: AsyncOpenAI,
    model: str,
    *,
    messages: list[dict[str, str]],
) -> AsyncIterator[str]:
    """Чат через Responses API с нативным web_search; диалог обрезается по бюджету токенов."""
    trimmed = trim_messages_for_responses(messages)
    input_text = dialog_to_responses_input(trimmed)
    if not input_text.strip():
        yield "Нет сообщений для ответа."
        return

    tools = yandex_responses_web_search_tools()
    try:
        stream = await client.responses.create(
            model=model,
            instructions=SYSTEM_CHAT,
            input=input_text,
            tools=tools,
            tool_choice="auto",
            stream=True,
            max_tool_calls=max_tool_calls_responses(),
            store=True,
        )
        yielded = False
        async for event in stream:
            if isinstance(event, ResponseTextDeltaEvent):
                if event.delta:
                    yielded = True
                    yield event.delta
            elif isinstance(event, ResponseErrorEvent):
                raise RuntimeError(event.message)
            elif isinstance(event, ResponseFailedEvent):
                raise RuntimeError("Responses API: response.failed")

        if not yielded:
            resp = await client.responses.create(
                model=model,
                instructions=SYSTEM_CHAT,
                input=input_text,
                tools=tools,
                tool_choice="auto",
                stream=False,
                max_tool_calls=max_tool_calls_responses(),
                store=True,
            )
            text = (getattr(resp, "output_text", None) or "").strip()
            if text:
                yield text
                return
            raise RuntimeError(
                "Пустой ответ Responses API (нет текстовых дельт). "
                "Проверьте, что модель и endpoint поддерживают Responses + web_search."
            )
    except APIError as e:
        raise RuntimeError(f"Ошибка LLM: {e}") from e
