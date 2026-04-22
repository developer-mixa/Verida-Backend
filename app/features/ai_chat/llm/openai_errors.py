from __future__ import annotations

import json
from typing import Any

from openai import APIError, APIStatusError


def format_openai_api_error(err: APIError) -> str:
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
