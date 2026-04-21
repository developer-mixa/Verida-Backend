from __future__ import annotations

import json
import os
import re
from collections.abc import AsyncIterator
from typing import Any

from openai import APIError, APIStatusError, AsyncOpenAI
from openai.types.responses import (
    ResponseErrorEvent,
    ResponseFailedEvent,
    ResponseTextDeltaEvent,
)

from app.features.ai_chat.llm.yandex_web_search_tools import yandex_responses_web_search_tools

# Запас под instructions, tools и «раздувание» после web_search (лимит модели часто 32768 суммарно).
_DEFAULT_DIALOGUE_TOKEN_BUDGET = 14_000


def _approx_tokens(text: str) -> int:
    """Грубая оценка токенов (RU/EN), без tiktoken: ~3 символа на токен."""
    if not text:
        return 0
    return max(1, (len(text) + 2) // 3)


def _dialogue_token_budget() -> int:
    raw = (os.getenv("YANDEX_CHAT_MAX_DIALOGUE_TOKENS") or "").strip()
    if raw.isdigit():
        v = int(raw)
        return max(2_000, min(v, 28_000))
    return _DEFAULT_DIALOGUE_TOKEN_BUDGET


def _max_tool_calls_responses() -> int:
    raw = (os.getenv("YANDEX_RESPONSES_MAX_TOOL_CALLS") or "").strip()
    if raw.isdigit():
        return max(1, min(int(raw), 8))
    return 4


def _trim_messages_for_responses(messages: list[dict[str, str]]) -> list[dict[str, str]]:
    """Сохраняет конец диалога в бюджете токенов (старые реплики отбрасываются)."""
    budget = _dialogue_token_budget()
    selected: list[dict[str, str]] = []
    used = 0
    for m in reversed(messages):
        role = str(m.get("role", ""))
        content = str(m.get("content", "")).strip()
        if not content or role not in ("user", "assistant"):
            continue
        cost = _approx_tokens(content) + 4
        if not selected and cost > budget:
            max_chars = max((budget - 4) * 3, 400)
            if len(content) > max_chars:
                content = content[:max_chars] + "\n…[обрезано по лимиту токенов]"
            cost = _approx_tokens(content) + 4
            selected.append({"role": role, "content": content})
            break
        if used + cost > budget:
            break
        used += cost
        selected.append({"role": role, "content": content})
    return list(reversed(selected))


def _normalize_tool_arguments_json(raw: str) -> str:
    """Убирает markdown-обёртку ```json ... ``` если модель вернула её в arguments."""
    s = (raw or "").strip()
    if s.startswith("```"):
        s = re.sub(r"^```[a-zA-Z]*\s*", "", s)
        s = re.sub(r"\s*```\s*$", "", s)
    return s.strip()


def _format_openai_api_error(err: APIError) -> str:
    """Человекочитаемое сообщение (Yandex часто кладёт детали в body, а не в message)."""
    parts: list[str] = [err.message or type(err).__name__]
    if isinstance(err, APIStatusError):
        parts.append(f"HTTP {err.status_code}")
        if err.request_id:
            parts.append(f"x-request-id={err.request_id}")
    if err.body is not None:
        if isinstance(err.body, str):
            body_s = err.body[:2500]
        else:
            try:
                body_s = json.dumps(err.body, ensure_ascii=False)[:2500]
            except (TypeError, ValueError):
                body_s = str(err.body)[:2500]
        parts.append(f"body={body_s}")
    return " | ".join(parts)


def _build_synopsis_result(data: dict[str, Any]) -> dict[str, str | list[dict[str, str]]]:
    title = str(data.get("title", "")).strip()
    content = str(data.get("content", "")).strip()
    if not title or not content:
        raise RuntimeError("В save_synopsis пустые title или content")
    tags_raw = data.get("tags")
    tags: list[dict[str, str]] = []
    if isinstance(tags_raw, list):
        for item in tags_raw:
            if not isinstance(item, dict):
                continue
            at = str(item.get("article_type", "")).strip()[:128]
            an = str(item.get("article_name", "")).strip()[:255]
            if at and an:
                tags.append({"article_type": at, "article_name": an})
    if not tags:
        raise RuntimeError("В save_synopsis нужен непустой массив tags")
    return {"title": title, "content": content, "tags": tags}


def _normalize_synopsis_tool_arguments(obj: Any) -> str | None:
    """
    Приводит объект аргументов save_synopsis к канонической JSON-строке для json.loads downstream.
    Допускает неполный объект (только content) — типично для текстового [TOOL_CALL_START] от Yandex.
    """
    if not isinstance(obj, dict):
        return None
    content = str(obj.get("content", "")).strip()
    if not content:
        return None
    title = str(obj.get("title", "")).strip()
    if not title:
        for line in content.splitlines():
            t = line.strip().lstrip("#*` ").strip()
            if t:
                title = t[:200]
                break
    if not title:
        title = "Конспект"
    tags: list[dict[str, str]] = []
    tags_raw = obj.get("tags")
    if isinstance(tags_raw, list):
        for item in tags_raw:
            if not isinstance(item, dict):
                continue
            at = str(item.get("article_type", "")).strip()[:128]
            an = str(item.get("article_name", "")).strip()[:255]
            if at and an:
                tags.append({"article_type": at, "article_name": an})
    if not tags:
        tags.append(
            {"article_type": "general", "article_name": (title[:120] or "Конспект диалога")}
        )
    return json.dumps({"title": title, "content": content, "tags": tags}, ensure_ascii=False)


def _fix_json_invalid_backslash_apostrophe(blob: str) -> str:
    """JSON не допускает \\'; модели вставляют LaTeX вроде $g\\'(x)$ внутри строк."""
    return re.sub(r"\\(?=')", "", blob)


def _relax_model_json_in_tool_chunk(blob: str) -> str:
    """Убирает типичные для LaTeX/Markdown в JSON невалидные escape-последовательности."""
    s = _fix_json_invalid_backslash_apostrophe(blob)
    prev = None
    while prev != s:
        prev = s
        # `\ ` и `\␉` в JSON недопустимы; модель часто пишет `\ neq` или обрывает `\neq`.
        s = re.sub(r"\\(?=[ \t])", "", s)
    return s


def _extract_content_string_from_save_synopsis_chunk(chunk: str) -> str | None:
    """
    Вытаскивает значение \"content\" из куска save_synopsis даже если JSON обрезан
    или не парсится (нет закрывающей `}` / `\"`).
    """
    key = '"content"'
    pos = chunk.find(key)
    if pos == -1:
        return None
    i = pos + len(key)
    n = len(chunk)
    while i < n and chunk[i] in " \t\r\n":
        i += 1
    if i >= n or chunk[i] != ":":
        return None
    i += 1
    while i < n and chunk[i] in " \t\r\n":
        i += 1
    if i >= n or chunk[i] != '"':
        return None
    i += 1
    out: list[str] = []
    while i < n:
        c = chunk[i]
        if c == '"':
            break
        if c == "\\" and i + 1 < n:
            nxt = chunk[i + 1]
            if nxt == "\\":
                out.append("\\")
                i += 2
                continue
            if nxt == "'":
                out.append("'")
                i += 2
                continue
            # LaTeX \\neq в JSON часто как \\n + eq, а не перевод строки.
            if nxt == "n" and i + 3 < n and chunk[i + 2 : i + 4] == "eq":
                out.append("\\neq")
                i += 4
                continue
            if nxt == "n":
                out.append("\n")
                i += 2
                continue
            if nxt == "t":
                out.append("\t")
                i += 2
                continue
            if nxt == "r":
                out.append("\r")
                i += 2
                continue
            if nxt in '\\"/':
                out.append(nxt)
                i += 2
                continue
            if nxt == "u" and i + 5 < n:
                hx = chunk[i + 2 : i + 6]
                if len(hx) == 4 and all(x in "0123456789abcdefABCDEF" for x in hx):
                    try:
                        out.append(chr(int(hx, 16)))
                    except ValueError:
                        out.append(nxt)
                        i += 2
                        continue
                    i += 6
                    continue
            out.append(nxt)
            i += 2
            continue
        out.append(c)
        i += 1
    text = "".join(out).strip()
    return text or None


def _try_yandex_tool_call_save_synopsis(s: str, decoder: json.JSONDecoder) -> str | None:
    """
    Yandex Assistant иногда отдаёт вызов инструмента в виде текста:
    [TOOL_CALL_START]save_synopsis {...}[TOOL_CALL_END]
    """
    for m in re.finditer(r"\[TOOL_CALL_START\]\s*save_synopsis\s*(\{)", s, re.IGNORECASE | re.DOTALL):
        brace = m.start(1)
        end_m = s.find("[TOOL_CALL_END]", brace)
        chunk = s[brace : end_m if end_m != -1 else len(s)]
        chunk = chunk.strip()
        blob_variants = (
            chunk,
            _fix_json_invalid_backslash_apostrophe(chunk),
            _relax_model_json_in_tool_chunk(chunk),
        )
        seen: set[str] = set()
        for blob in blob_variants:
            if blob in seen:
                continue
            seen.add(blob)
            if not blob.startswith("{"):
                continue
            try:
                obj, _ = decoder.raw_decode(blob, 0)
            except json.JSONDecodeError:
                pass
            else:
                got = _normalize_synopsis_tool_arguments(obj)
                if got:
                    return got
        extracted = _extract_content_string_from_save_synopsis_chunk(chunk)
        if extracted:
            got = _normalize_synopsis_tool_arguments({"content": extracted})
            if got:
                return got
    return None


def _save_synopsis_arguments_from_chat_message(choice: Any) -> str:
    if not choice.tool_calls:
        raise RuntimeError(
            "Модель не вернула вызов save_synopsis. "
            "Проверьте, что endpoint поддерживает function calling в chat.completions."
        )
    for tc in choice.tool_calls:
        if tc.function.name == "save_synopsis":
            return _normalize_tool_arguments_json(tc.function.arguments or "{}")
    names = [tc.function.name for tc in choice.tool_calls]
    raise RuntimeError(f"Ожидался save_synopsis, получены tools: {names}")


def _responses_assistant_plain_text(resp: Any) -> str:
    """Текст финального сообщения из output (без SDK Response — удобно для тестов)."""
    texts: list[str] = []
    for output in getattr(resp, "output", None) or []:
        if getattr(output, "type", None) != "message":
            continue
        for content in getattr(output, "content", None) or []:
            if getattr(content, "type", None) == "output_text":
                t = getattr(content, "text", None)
                if t:
                    texts.append(str(t))
    return "".join(texts)


def _synopsis_json_string_from_plain_text(text: str) -> str | None:
    """
    Если модель вернула конспект текстом (без function_call), вытащить JSON с полями
    title, content, tags — цельный объект или в ```json ... ```, или после преамбулы.
    """
    s = (text or "").strip()
    if not s:
        return None
    decoder = json.JSONDecoder()

    got = _try_yandex_tool_call_save_synopsis(s, decoder)
    if got:
        return got

    def try_decode(blob: str) -> str | None:
        blob = blob.strip()
        if not blob:
            return None
        if blob.startswith("{"):
            cand_seen: set[str] = set()
            for candidate in (
                blob,
                _fix_json_invalid_backslash_apostrophe(blob),
                _relax_model_json_in_tool_chunk(blob),
            ):
                if candidate in cand_seen:
                    continue
                cand_seen.add(candidate)
                try:
                    obj = json.loads(_normalize_tool_arguments_json(candidate))
                    got = _normalize_synopsis_tool_arguments(obj)
                    if got:
                        return got
                except json.JSONDecodeError:
                    pass
                try:
                    obj, _ = decoder.raw_decode(candidate, 0)
                    got = _normalize_synopsis_tool_arguments(obj)
                    if got:
                        return got
                except json.JSONDecodeError:
                    pass
        return None

    norm = _normalize_tool_arguments_json(s)
    got = try_decode(norm)
    if got:
        return got

    m = re.search(r"```(?:json)?\s*([\s\S]*?)\s*```", s, re.IGNORECASE)
    if m:
        inner = m.group(1).strip()
        got = try_decode(inner)
        if got:
            return got

    title_at = s.find('"title"')
    if title_at != -1:
        b = s.rfind("{", 0, title_at)
        if b != -1:
            tail_seen: set[str] = set()
            for candidate in (
                s[b:],
                _fix_json_invalid_backslash_apostrophe(s[b:]),
                _relax_model_json_in_tool_chunk(s[b:]),
            ):
                if candidate in tail_seen:
                    continue
                tail_seen.add(candidate)
                try:
                    obj, _ = decoder.raw_decode(candidate, 0)
                    got = _normalize_synopsis_tool_arguments(obj)
                    if got:
                        return got
                except json.JSONDecodeError:
                    pass

    j = 0
    while True:
        b = s.find("{", j)
        if b == -1:
            break
        parsed_any = False
        slice_seen: set[str] = set()
        for candidate in (
            s[b:],
            _fix_json_invalid_backslash_apostrophe(s[b:]),
            _relax_model_json_in_tool_chunk(s[b:]),
        ):
            if candidate in slice_seen:
                continue
            slice_seen.add(candidate)
            try:
                obj, end_rel = decoder.raw_decode(candidate, 0)
            except json.JSONDecodeError:
                continue
            parsed_any = True
            got = _normalize_synopsis_tool_arguments(obj)
            if got:
                return got
            j = b + end_rel
            break
        if not parsed_any:
            j = b + 1

    # Обрезанный JSON в ``` { ... без закрывающих ```/`}` — всё ещё можно достать content.
    probe_seen: set[str] = set()
    for probe in (
        norm,
        _relax_model_json_in_tool_chunk(norm),
        s,
        _relax_model_json_in_tool_chunk(s),
    ):
        if not probe or probe in probe_seen:
            continue
        probe_seen.add(probe)
        extracted = _extract_content_string_from_save_synopsis_chunk(probe)
        if extracted:
            got = _normalize_synopsis_tool_arguments({"content": extracted})
            if got:
                return got
    return None


def _save_synopsis_arguments_from_response(resp: Any) -> str:
    err = getattr(resp, "error", None)
    if err is not None:
        raise RuntimeError(f"Response.error: {getattr(err, 'code', '')} {getattr(err, 'message', err)}")
    out = getattr(resp, "output", None) or []
    for item in out:
        if getattr(item, "type", None) == "function_call" and getattr(item, "name", None) == "save_synopsis":
            return _normalize_tool_arguments_json(getattr(item, "arguments", "") or "{}")
    plain = _responses_assistant_plain_text(resp).strip()
    if plain:
        extracted = _synopsis_json_string_from_plain_text(plain)
        if extracted:
            return extracted
    kinds = [getattr(item, "type", "?") for item in out]
    snippet = plain[:400].replace("\n", " ")
    raise RuntimeError(
        "Нет function_call save_synopsis и не удалось извлечь JSON конспекта из текста ответа "
        f"(элементы output: {kinds}; status={getattr(resp, 'status', None)}; фрагмент: {snippet!r})"
    )


def _trim_dialogue_block(dialogue_block: str) -> str:
    """Для конспекта: один текст переписки не шире бюджета (хвост сохраняется)."""
    budget = _dialogue_token_budget()
    if _approx_tokens(dialogue_block) <= budget:
        return dialogue_block
    max_chars = max(budget * 3 - 200, 500)
    tail = dialogue_block[-max_chars:]
    return "…[начало переписки убрано из‑за лимита токенов]\n\n" + tail


_SAVE_SYNOPSIS_TOOL_DESCRIPTION = (
    "Сохрани конспект диалога в базу. Вызови один раз, когда текст конспекта готов. "
    "Поле content — в Markdown. Укажи релевантные теги: article_type только на английском "
    "(латиница, короткий ключ: biology, chemistry, methodology и т.п.), article_name — "
    "человекочитаемая подпись (может быть на языке пользователя)."
)

_SAVE_SYNOPSIS_TOOL_PARAMETERS: dict[str, Any] = {
    "type": "object",
    "properties": {
        "title": {
            "type": "string",
            "description": "Краткий заголовок конспекта",
        },
        "content": {
            "type": "string",
            "description": "Полный текст конспекта в Markdown",
        },
        "tags": {
            "type": "array",
            "minItems": 1,
            "maxItems": 24,
            "description": "Теги статьи; article_type — только английский ключ",
            "items": {
                "type": "object",
                "properties": {
                    "article_type": {
                        "type": "string",
                        "description": "English-only type key, e.g. biology, physics, methodology",
                    },
                    "article_name": {
                        "type": "string",
                        "description": "Display name for the tag (any language)",
                    },
                },
                "required": ["article_type", "article_name"],
            },
        },
    },
    "required": ["title", "content", "tags"],
}

# Формат chat.completions (OpenAI): name внутри `function`.
SAVE_SYNOPSIS_OPENAI_TOOL: dict[str, Any] = {
    "type": "function",
    "function": {
        "name": "save_synopsis",
        "description": _SAVE_SYNOPSIS_TOOL_DESCRIPTION,
        "parameters": _SAVE_SYNOPSIS_TOOL_PARAMETERS,
    },
}

# Формат Responses API / Yandex (как log_exercise_tool в yandex-ai-studio/fitness-assistant):
# плоский объект type/name/description/parameters, без вложенного `function`.
SAVE_SYNOPSIS_RESPONSES_TOOL: dict[str, Any] = {
    "type": "function",
    "name": "save_synopsis",
    "description": _SAVE_SYNOPSIS_TOOL_DESCRIPTION,
    "parameters": _SAVE_SYNOPSIS_TOOL_PARAMETERS,
}

_SCIENCE_CHAT_TOOLS_HINT = (
    "У тебя один инструмент веб-поиска Яндекса (Responses API, type web_search). "
    "Сначала формулируй запросы так, чтобы получить данные из научной литературы и авторитетных источников "
    "(PubMed, журналы, DOI, arXiv, препринты, обзоры). При недостатке релевантных результатов делай "
    "дополнительные вызовы поиска с более широкой или общей формулировкой по тому же инструменту. "
    "Не выдумывай URL и цитаты — опирайся на выдачу поиска; указывай неуверенность, если источники слабые."
)

_SYNOPSIS_SCOPE_HINT = (
    "Опирайся только на текст переписки ниже; не добавляй внешние статьи и цитаты, которых нет в диалоге."
)

_SYSTEM_CHAT = (
    "Ты научный ассистент Verida: отвечай ясно, по-русски, в доступном научном стиле. "
    "Не выдумывай факты; если данных мало — так и скажи. "
    + _SCIENCE_CHAT_TOOLS_HINT
)

_SYSTEM_SYNOPSIS = (
    "Ты составляешь конспект переписки для пользователя. "
    + _SYNOPSIS_SCOPE_HINT
    + (
        " Обязательно вызови функцию save_synopsis с полным конспектом в Markdown в поле content, "
        "коротким заголовком в title и массивом tags (минимум один тег). "
        "Для каждого тега поле article_type — только английский идентификатор "
        "(латинские буквы, цифры, подчёркивание; нижний регистр), например neuroscience, lab_safety. "
        "Поле article_name — короткая подпись тега на языке конспекта (как в параметре языка). "
        "Не пиши конспект только в свободном тексте без вызова функции."
    )
)


def _dialog_to_responses_input(messages: list[dict[str, str]]) -> str:
    """Текст диалога для поля `input` Responses API (system задаётся отдельно в `instructions`)."""
    parts: list[str] = []
    for m in messages:
        role = m.get("role", "")
        content = (m.get("content") or "").strip()
        if not content:
            continue
        if role == "user":
            parts.append(f"Пользователь:\n{content}")
        elif role == "assistant":
            parts.append(f"Ассистент:\n{content}")
    return "\n\n".join(parts)


async def _yandex_responses_synopsis_tool_follow_up(
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
        """Чат через Responses API с нативным web_search; диалог обрезается по бюджету токенов."""
        trimmed = _trim_messages_for_responses(messages)
        input_text = _dialog_to_responses_input(trimmed)
        if not input_text.strip():
            yield "Нет сообщений для ответа."
            return

        tools = yandex_responses_web_search_tools()
        try:
            stream = await self._client.responses.create(
                model=self._model,
                instructions=_SYSTEM_CHAT,
                input=input_text,
                tools=tools,
                tool_choice="auto",
                stream=True,
                max_tool_calls=_max_tool_calls_responses(),
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
                resp = await self._client.responses.create(
                    model=self._model,
                    instructions=_SYSTEM_CHAT,
                    input=input_text,
                    tools=tools,
                    tool_choice="auto",
                    stream=False,
                    max_tool_calls=_max_tool_calls_responses(),
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

    async def synopsis_save_args(
        self, *, dialogue_block: str, language: str | None
    ) -> dict[str, str | list[dict[str, str]]]:
        lang = language or "ru"
        dialogue_block = _trim_dialogue_block(dialogue_block)
        user_prompt = (
            f"Язык ответа конспекта: {lang}.\n\n"
            f"Ниже переписка (от старых сообщений к новым). Составь конспект и вызови save_synopsis.\n\n"
            f"{dialogue_block}"
        )
        messages = [
            {"role": "system", "content": _SYSTEM_SYNOPSIS},
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
            r = await self._client.responses.create(
                model=self._model,
                instructions=_SYSTEM_SYNOPSIS,
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
            await _yandex_responses_synopsis_tool_follow_up(
                self._client, model=self._model, first_response=r
            )
            return result
        except APIError as e:
            failures.append(f"responses: {_format_openai_api_error(e)}")
        except (RuntimeError, json.JSONDecodeError, KeyError, TypeError) as e:
            failures.append(f"responses: {e}")

        # 2) chat.completions + принудительный tool
        try:
            resp = await self._client.chat.completions.create(
                model=self._model,
                messages=messages,
                tools=[SAVE_SYNOPSIS_OPENAI_TOOL],
                tool_choice=tool_choice_chat_forced,
                temperature=0.2,
            )
            raw = _save_synopsis_arguments_from_chat_message(resp.choices[0].message)
            data = json.loads(raw)
            return _build_synopsis_result(data)
        except APIError as e:
            failures.append(f"chat(forced): {_format_openai_api_error(e)}")
        except (RuntimeError, json.JSONDecodeError, KeyError, TypeError) as e:
            failures.append(f"chat(forced): {e}")

        # 3) chat.completions + auto
        try:
            resp = await self._client.chat.completions.create(
                model=self._model,
                messages=messages,
                tools=[SAVE_SYNOPSIS_OPENAI_TOOL],
                tool_choice="auto",
                temperature=0.2,
            )
            raw = _save_synopsis_arguments_from_chat_message(resp.choices[0].message)
            data = json.loads(raw)
            return _build_synopsis_result(data)
        except APIError as e:
            failures.append(f"chat(auto): {_format_openai_api_error(e)}")
        except (RuntimeError, json.JSONDecodeError, KeyError, TypeError) as e:
            failures.append(f"chat(auto): {e}")

        raise RuntimeError("Ошибка LLM (synopsis), все варианты: " + " || ".join(failures))
