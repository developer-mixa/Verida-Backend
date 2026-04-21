from __future__ import annotations

import json
from types import SimpleNamespace

import pytest

from app.features.ai_chat.llm import openai_chat_llm as llm


def _resp_only_message(text: str) -> SimpleNamespace:
    msg = SimpleNamespace(
        type="message",
        content=[SimpleNamespace(type="output_text", text=text)],
    )
    return SimpleNamespace(error=None, output=[msg], status="completed")


def test_save_synopsis_from_response_plain_json() -> None:
    body = (
        '{"title":"T","content":"C","tags":[{"article_type":"bio","article_name":"Жизнь"}]}'
    )
    raw = llm._save_synopsis_arguments_from_response(_resp_only_message(body))
    data = json.loads(raw)
    assert data["title"] == "T"
    assert data["content"] == "C"
    assert data["tags"][0]["article_type"] == "bio"


def test_save_synopsis_from_response_fenced_and_preamble() -> None:
    body = """Вот данные:
```json
{"title":"X","content":"Y","tags":[{"article_type":"m","article_name":"N"}]}
```
"""
    raw = llm._save_synopsis_arguments_from_response(_resp_only_message(body))
    assert json.loads(raw)["title"] == "X"


def test_save_synopsis_function_call_wins_over_message() -> None:
    fc = SimpleNamespace(
        type="function_call",
        name="save_synopsis",
        arguments='{"title":"A","content":"B","tags":[{"article_type":"t","article_name":"n"}]}',
    )
    wrong_msg = SimpleNamespace(
        type="message",
        content=[
            SimpleNamespace(
                type="output_text",
                text='{"title":"wrong","content":"w","tags":[{"article_type":"t","article_name":"n"}]}',
            )
        ],
    )
    resp = SimpleNamespace(error=None, output=[wrong_msg, fc], status="completed")
    raw = llm._save_synopsis_arguments_from_response(resp)
    assert json.loads(raw)["title"] == "A"


def test_save_synopsis_from_response_raises_without_json() -> None:
    with pytest.raises(RuntimeError, match="не удалось извлечь"):
        llm._save_synopsis_arguments_from_response(_resp_only_message("Просто текст без JSON."))


def test_yandex_tool_call_marker_with_optional_end_tag() -> None:
    inner = (
        '{"title":"Лопиталь","content":"**Правило**\\nтекст","tags":'
        '[{"article_type":"mathematics","article_name":"Пределы"}]}'
    )
    body = f"[TOOL_CALL_START]save_synopsis {inner}[TOOL_CALL_END] хвост"
    raw = llm._save_synopsis_arguments_from_response(_resp_only_message(body))
    data = json.loads(raw)
    assert data["title"] == "Лопиталь"
    assert "Правило" in data["content"]


def test_yandex_tool_call_marker_content_only_gets_defaults() -> None:
    inner = '{"content":"## Только текст\\n\\nабзац."}'
    body = f"[TOOL_CALL_START]save_synopsis {inner}"
    raw = llm._save_synopsis_arguments_from_response(_resp_only_message(body))
    data = json.loads(raw)
    assert data["content"].startswith("##")
    assert data["tags"][0]["article_type"] == "general"


def test_yandex_tool_call_truncated_malformed_still_extracts_content() -> None:
    """Обрыв JSON и невалидные escape внутри content — как в логах Yandex (\\' и \\ перед пробелом)."""
    piece = "**Правило** g" + r"\'" + "(x) " + r"\ " + "eq 0 дальше текст без закрывающей кавычки"
    body = '[TOOL_CALL_START]save_synopsis {"content":"' + piece
    raw = llm._synopsis_json_string_from_plain_text(body)
    assert raw is not None
    data = json.loads(raw)
    assert "**Правило**" in data["content"]
    assert "g'(x)" in data["content"]


def test_unclosed_markdown_fence_truncated_json_still_extracts_content() -> None:
    """Модель: ``` { "title":..., "content":"... без ``` и без `}` (как в логах Yandex)."""
    s = (
        '``` {   "title": "Правило Лопиталя",   "content": "**Правило**\\n $g'
        + "\\"
        + "'"
        + r"(x) \neq 0$ хвост"
    )
    raw = llm._synopsis_json_string_from_plain_text(s)
    assert raw is not None
    data = json.loads(raw)
    assert "Правило" in data["content"]
    assert "neq" in data["content"]


def test_relax_model_json_removes_backslash_before_space() -> None:
    raw_in = '{"title":"T","content":"a\\ bc","tags":[{"article_type":"m","article_name":"n"}]}'
    with pytest.raises(json.JSONDecodeError):
        json.loads(raw_in)
    relaxed = llm._relax_model_json_in_tool_chunk(raw_in)
    obj = json.loads(relaxed)
    assert obj["content"] == "a bc"


def test_fix_json_invalid_backslash_apostrophe() -> None:
    # Невалидный JSON: внутри строки LaTeX-стиль \' (не по спецификации JSON).
    bad = (
        '{"title":"T","content":"gBAD","tags":[{"article_type":"m","article_name":"n"}]}'.replace(
            "BAD", r"\'(x)"
        )
    )
    with pytest.raises(json.JSONDecodeError):
        json.loads(bad)
    fixed = llm._fix_json_invalid_backslash_apostrophe(bad)
    obj = json.loads(fixed)
    raw = llm._normalize_synopsis_tool_arguments(obj)
    assert raw is not None
    assert "g'(x)" in json.loads(raw)["content"]
