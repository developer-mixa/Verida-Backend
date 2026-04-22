from __future__ import annotations

import json
from typing import Any

from openai import APIError, AsyncOpenAI

from app.features.ai_chat.llm.dialogue_limits import trim_dialogue_block
from app.features.ai_chat.llm.openai_errors import format_openai_api_error
from app.features.ai_chat.llm.synopsis_response_parse import (
    _build_synopsis_result,
    _save_synopsis_arguments_from_response,
)
from app.features.ai_chat.llm.synopsis_tool_spec import SAVE_SYNOPSIS_RESPONSES_TOOL, SYSTEM_SYNOPSIS


async def _responses_synopsis_tool_follow_up(
    client: AsyncOpenAI,
    *,
    model: str,
    first_response: Any,
) -> None:
    """
    Второй вызов responses.create: input с элементами type=function_call_output (как в Yandex rest-assistant).
    Текст follow-up для Verida не используется; нужен для протокола tool calling.
    """
    rid = getattr(first_response, "id", None)
    if not rid:
        return

    tool_list = [SAVE_SYNOPSIS_RESPONSES_TOOL]
    out: list[dict[str, Any]] = []
    for item in getattr(first_response, "output", None) or []:
        if getattr(item, "type", None) != "function_call":
            continue
        if getattr(item, "name", None) != "save_synopsis":
            continue
        call_id = getattr(item, "call_id", None)
        if not call_id:
            continue
        result_payload = json.dumps({"status": "success"}, ensure_ascii=False)
        out.append(
            {
                "type": "function_call_output",
                "call_id": call_id,
                "output": result_payload,
            }
        )

    if not out:
        return

    try:
        await client.responses.create(
            model=model,
            store=True,
            previous_response_id=str(rid),
            input=out,
            tools=tool_list,
            tool_choice="auto",
        )
    except APIError:
        pass


async def run_synopsis_save_args(
    client: AsyncOpenAI,
    model: str,
    *,
    dialogue_block: str,
    language: str | None,
) -> dict[str, str | list[dict[str, str]]]:
    lang = language or "ru"
    dialogue_block = trim_dialogue_block(dialogue_block)
    user_prompt = (
        f"Язык ответа конспекта: {lang}.\n\n"
        f"Ниже переписка (от старых сообщений к новым). Составь конспект и вызови save_synopsis.\n\n"
        f"{dialogue_block}"
    )

    try:
        r = await client.responses.create(
            model=model,
            instructions=SYSTEM_SYNOPSIS,
            input=user_prompt,
            tools=[SAVE_SYNOPSIS_RESPONSES_TOOL],
            tool_choice="auto",
            stream=False,
            temperature=0.2,
            max_tool_calls=3,
            store=True,
        )
        raw = _save_synopsis_arguments_from_response(r)
        data = json.loads(raw)
        result = _build_synopsis_result(data)
        await _responses_synopsis_tool_follow_up(client, model=model, first_response=r)
        return result
    except APIError as e:
        raise RuntimeError(f"Ошибка LLM (synopsis): {format_openai_api_error(e)}") from e
    except (RuntimeError, json.JSONDecodeError, KeyError, TypeError) as e:
        raise RuntimeError(f"Ошибка LLM (synopsis): {e}") from e
