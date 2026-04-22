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


def _resp_with_synopsis_fc(arguments: str, *, call_id: str = "call-1") -> SimpleNamespace:
    fc = SimpleNamespace(
        type="function_call",
        name="save_synopsis",
        arguments=arguments,
        call_id=call_id,
    )
    return SimpleNamespace(error=None, output=[fc], status="completed")


def test_save_synopsis_from_function_call() -> None:
    arguments = (
        '{"title":"T","content":"C","tags":[{"article_type":"bio","article_name":"Жизнь"}]}'
    )
    raw = llm._save_synopsis_arguments_from_response(_resp_with_synopsis_fc(arguments))
    data = json.loads(raw)
    assert data["title"] == "T"
    assert data["content"] == "C"
    assert data["tags"][0]["article_type"] == "bio"


def test_function_call_wins_over_message_in_output() -> None:
    fc = SimpleNamespace(
        type="function_call",
        name="save_synopsis",
        arguments='{"title":"A","content":"B","tags":[{"article_type":"t","article_name":"n"}]}',
        call_id="c1",
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


def test_message_only_raises() -> None:
    with pytest.raises(RuntimeError, match="function_call save_synopsis"):
        llm._save_synopsis_arguments_from_response(_resp_only_message("Просто текст."))


def test_invalid_json_in_arguments_raises() -> None:
    with pytest.raises(RuntimeError, match="JSON-объектом"):
        llm._save_synopsis_arguments_from_response(_resp_with_synopsis_fc("{not json"))
