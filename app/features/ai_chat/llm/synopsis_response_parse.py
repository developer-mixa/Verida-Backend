from __future__ import annotations

import json
from typing import Any


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


def parse_synopsis_from_response(resp: Any) -> dict[str, str | list[dict[str, str]]]:
    """
    Только output Responses API: type=function_call, name=save_synopsis.
    Поле arguments — валидный JSON-объект (как отдаёт API после вызова инструмента), без доразбора и обёрток.
    """
    err = getattr(resp, "error", None)
    if err is not None:
        raise RuntimeError(f"Response.error: {getattr(err, 'code', '')} {getattr(err, 'message', err)}")

    out = getattr(resp, "output", None) or []
    for item in out:
        if getattr(item, "type", None) != "function_call":
            continue
        if getattr(item, "name", None) != "save_synopsis":
            continue
        raw_args = getattr(item, "arguments", None)
        if isinstance(raw_args, str):
            try:
                data = json.loads(raw_args.strip())
            except json.JSONDecodeError as e:
                raise RuntimeError(
                    "save_synopsis.arguments должны быть одним JSON-объектом без markdown и преамбул. "
                    f"Ошибка парсинга: {e}"
                ) from e
        elif isinstance(raw_args, dict):
            data = raw_args
        else:
            raise RuntimeError(f"save_synopsis: неожиданный тип arguments: {type(raw_args).__name__}")
        if not isinstance(data, dict):
            raise RuntimeError("save_synopsis: arguments после парсинга должны быть объектом")
        return _build_synopsis_result(data)

    kinds = [getattr(item, "type", "?") for item in out]
    raise RuntimeError(
        "Ожидался function_call save_synopsis в output ответа. "
        f"Получено: {kinds}. Модель должна вызвать save_synopsis с корректным JSON в arguments."
    )


def _save_synopsis_arguments_from_response(resp: Any) -> str:
    """JSON-строка аргументов (тесты и обратная совместимость)."""
    return json.dumps(parse_synopsis_from_response(resp), ensure_ascii=False)
