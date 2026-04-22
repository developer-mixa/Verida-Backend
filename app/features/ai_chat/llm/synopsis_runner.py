from __future__ import annotations

import json
import logging
from typing import Any

from openai import APIError, AsyncOpenAI

# TODO(remove): временный отладочный лог ответа Responses API (см. _log_synopsis_responses_debug).
_synopsis_debug_log = logging.getLogger(__name__)

from app.features.ai_chat.llm.dialogue_limits import trim_dialogue_block
from app.features.ai_chat.llm.openai_errors import format_openai_api_error
from app.features.ai_chat.llm.synopsis_response_parse import parse_synopsis_from_response
from app.features.ai_chat.llm.synopsis_tool_spec import (
    SAVE_SYNOPSIS_RESPONSES_TOOL,
    SYNOPSIS_INSTRUCTIONS,
)


def _serialize_synopsis_output_item(item: Any) -> dict[str, Any]:
    """TODO(remove): укладка одного элемента output для отладочного лога."""
    kind = getattr(item, "type", None)
    if kind == "function_call":
        args = getattr(item, "arguments", None)
        if isinstance(args, str) and len(args) > 6_000:
            args = args[:6_000] + "…(truncated)"
        return {
            "type": kind,
            "name": getattr(item, "name", None),
            "call_id": getattr(item, "call_id", None),
            "arguments": args,
        }
    if kind == "message":
        content = getattr(item, "content", None)
        blocks: list[Any] = []
        if isinstance(content, list):
            for block in content:
                if hasattr(block, "model_dump"):
                    try:
                        blocks.append(block.model_dump())
                    except Exception:
                        blocks.append(
                            {
                                "type": getattr(block, "type", None),
                                "text": getattr(block, "text", None),
                            }
                        )
                elif isinstance(block, dict):
                    blocks.append(block)
                else:
                    blocks.append(
                        {
                            "type": getattr(block, "type", None),
                            "text": getattr(block, "text", None),
                        }
                    )
        else:
            blocks.append(str(content)[:8_000] if content is not None else None)
        return {
            "type": kind,
            "role": getattr(item, "role", None),
            "status": getattr(item, "status", None),
            "content": blocks,
        }
    if hasattr(item, "model_dump"):
        try:
            return {"type": kind, "model_dump": item.model_dump()}
        except Exception:
            pass
    return {"type": kind, "repr": repr(item)[:4_000]}


def _log_synopsis_responses_debug(resp: Any) -> None:
    """TODO(remove): что именно вернул Responses API до парсинга save_synopsis."""
    out = getattr(resp, "output", None) or []
    payload: dict[str, Any] = {
        "response_id": getattr(resp, "id", None),
        "status": getattr(resp, "status", None),
        "error": getattr(resp, "error", None),
        "incomplete_details": getattr(resp, "incomplete_details", None),
        "output_kinds": [getattr(i, "type", "?") for i in out],
        "output": [_serialize_synopsis_output_item(i) for i in out],
        "output_text": getattr(resp, "output_text", None),
    }
    line = json.dumps(payload, ensure_ascii=False, default=str)
    if len(line) > 24_000:
        line = line[:24_000] + "…(log truncated)"
    _synopsis_debug_log.warning("TODO(remove) synopsis Responses debug: %s", line)


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
        f"Ниже переписка (от старых сообщений к новым). Составь конспект и вызови только save_synopsis.\n\n"
        f"{dialogue_block}"
    )

    try:
        r = await client.responses.create(
            model=model,
            instructions=SYNOPSIS_INSTRUCTIONS,
            input=user_prompt,
            tools=[SAVE_SYNOPSIS_RESPONSES_TOOL],
            tool_choice="auto",
            stream=False,
            temperature=0.2,
            max_tool_calls=3,
            store=True,
        )
        _log_synopsis_responses_debug(r)
        result = parse_synopsis_from_response(r)
        await _responses_synopsis_tool_follow_up(client, model=model, first_response=r)
        return result
    except APIError as e:
        raise RuntimeError(f"Ошибка LLM (synopsis): {format_openai_api_error(e)}") from e
    except (RuntimeError, json.JSONDecodeError, KeyError, TypeError) as e:
        raise RuntimeError(f"Ошибка LLM (synopsis): {e}") from e
