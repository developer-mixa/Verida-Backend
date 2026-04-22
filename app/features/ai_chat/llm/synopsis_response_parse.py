from __future__ import annotations

import json
import re
from typing import Any


def _normalize_tool_arguments_json(raw: str) -> str:
    """Убирает markdown-обёртку ```json ... ``` если модель вернула её в arguments."""
    s = (raw or "").strip()
    if s.startswith("```"):
        s = re.sub(r"^```[a-zA-Z]*\s*", "", s)
        s = re.sub(r"\s*```\s*$", "", s)
    return s.strip()


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
