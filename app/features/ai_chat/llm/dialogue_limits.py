from __future__ import annotations

import os

# Запас под instructions, tools и «раздувание» после web_search (лимит модели часто 32768 суммарно).
_DEFAULT_DIALOGUE_TOKEN_BUDGET = 14_000


def approx_tokens(text: str) -> int:
    """Грубая оценка токенов (RU/EN), без tiktoken: ~3 символа на токен."""
    if not text:
        return 0
    return max(1, (len(text) + 2) // 3)


def dialogue_token_budget() -> int:
    raw = (os.getenv("YANDEX_CHAT_MAX_DIALOGUE_TOKENS") or "").strip()
    if raw.isdigit():
        v = int(raw)
        return max(2_000, min(v, 28_000))
    return _DEFAULT_DIALOGUE_TOKEN_BUDGET


def max_tool_calls_responses() -> int:
    raw = (os.getenv("YANDEX_RESPONSES_MAX_TOOL_CALLS") or "").strip()
    if raw.isdigit():
        return max(1, min(int(raw), 8))
    return 4


def trim_messages_for_responses(messages: list[dict[str, str]]) -> list[dict[str, str]]:
    """Сохраняет конец диалога в бюджете токенов (старые реплики отбрасываются)."""
    budget = dialogue_token_budget()
    selected: list[dict[str, str]] = []
    used = 0
    for m in reversed(messages):
        role = str(m.get("role", ""))
        content = str(m.get("content", "")).strip()
        if not content or role not in ("user", "assistant"):
            continue
        cost = approx_tokens(content) + 4
        if not selected and cost > budget:
            max_chars = max((budget - 4) * 3, 400)
            if len(content) > max_chars:
                content = content[:max_chars] + "\n…[обрезано по лимиту токенов]"
            cost = approx_tokens(content) + 4
            selected.append({"role": role, "content": content})
            break
        if used + cost > budget:
            break
        used += cost
        selected.append({"role": role, "content": content})
    return list(reversed(selected))


def trim_dialogue_block(dialogue_block: str) -> str:
    """Для конспекта: один текст переписки не шире бюджета (хвост сохраняется)."""
    budget = dialogue_token_budget()
    if approx_tokens(dialogue_block) <= budget:
        return dialogue_block
    max_chars = max(budget * 3 - 200, 500)
    tail = dialogue_block[-max_chars:]
    return "…[начало переписки убрано из‑за лимита токенов]\n\n" + tail


def dialog_to_responses_input(messages: list[dict[str, str]]) -> str:
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
