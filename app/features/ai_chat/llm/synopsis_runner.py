from __future__ import annotations

import json
from typing import Any

from openai import APIError, AsyncOpenAI

from app.features.ai_chat.llm.dialogue_limits import trim_dialogue_block
from app.features.ai_chat.llm.openai_errors import format_openai_api_error
from app.features.ai_chat.llm.synopsis_response_parse import (
    _build_synopsis_result,
    _save_synopsis_arguments_from_chat_message,
    _save_synopsis_arguments_from_response,
)
from app.features.ai_chat.llm.synopsis_tool_spec import (
    SAVE_SYNOPSIS_OPENAI_TOOL,
    SAVE_SYNOPSIS_RESPONSES_TOOL,
    SYSTEM_SYNOPSIS,
)


async def yandex_responses_synopsis_tool_follow_up(
    client: AsyncOpenAI,
    *,
    model: str,
    first_response: Any,
) -> None:
    """
    Второй вызов responses.create с previous_response_id и текстом результата инструмента —
    как в yandex-ai-studio/fitness-assistant (building-blocks/tool-calling.ipynb).
    Не используется текст follow-up в ответе Verida; нужен для согласованности с протоколом Yandex.
    """
    rid = getattr(first_response, "id", None)
    if not rid:
        return
    payload = "Результат выполнения функции save_synopsis: " + json.dumps(
        {"status": "success"},
        ensure_ascii=False,
    )
    try:
        await client.responses.create(
            model=model,
            store=True,
            previous_response_id=str(rid),
            input=payload,
            stream=False,
            temperature=0.2,
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
    messages = [
        {"role": "system", "content": SYSTEM_SYNOPSIS},
        {"role": "user", "content": user_prompt},
    ]
    tool_choice_chat_forced: dict[str, object] = {
        "type": "function",
        "function": {"name": "save_synopsis"},
    }
    failures: list[str] = []

    # 1) Responses API — как в yandex-ai-studio/fitness-assistant: store=True, tool_choice=auto,
    #    затем при успехе — второй create с previous_response_id (результат «выполнения» save_synopsis).
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
        await yandex_responses_synopsis_tool_follow_up(client, model=model, first_response=r)
        return result
    except APIError as e:
        failures.append(f"responses: {format_openai_api_error(e)}")
    except (RuntimeError, json.JSONDecodeError, KeyError, TypeError) as e:
        failures.append(f"responses: {e}")

    # 2) chat.completions + принудительный tool
    try:
        resp = await client.chat.completions.create(
            model=model,
            messages=messages,
            tools=[SAVE_SYNOPSIS_OPENAI_TOOL],
            tool_choice=tool_choice_chat_forced,
            temperature=0.2,
        )
        raw = _save_synopsis_arguments_from_chat_message(resp.choices[0].message)
        data = json.loads(raw)
        return _build_synopsis_result(data)
    except APIError as e:
        failures.append(f"chat(forced): {format_openai_api_error(e)}")
    except (RuntimeError, json.JSONDecodeError, KeyError, TypeError) as e:
        failures.append(f"chat(forced): {e}")

    # 3) chat.completions + auto
    try:
        resp = await client.chat.completions.create(
            model=model,
            messages=messages,
            tools=[SAVE_SYNOPSIS_OPENAI_TOOL],
            tool_choice="auto",
            temperature=0.2,
        )
        raw = _save_synopsis_arguments_from_chat_message(resp.choices[0].message)
        data = json.loads(raw)
        return _build_synopsis_result(data)
    except APIError as e:
        failures.append(f"chat(auto): {format_openai_api_error(e)}")
    except (RuntimeError, json.JSONDecodeError, KeyError, TypeError) as e:
        failures.append(f"chat(auto): {e}")

    raise RuntimeError("Ошибка LLM (synopsis), все варианты: " + " || ".join(failures))
