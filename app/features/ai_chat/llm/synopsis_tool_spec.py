from __future__ import annotations

from typing import Any

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

SYSTEM_SYNOPSIS = (
    "Ты составляешь конспект переписки для пользователя. "
    "Опирайся только на текст переписки ниже; не добавляй внешние статьи и цитаты, которых нет в диалоге."
    + (
        " Обязательно вызови функцию save_synopsis с полным конспектом в Markdown в поле content, "
        "коротким заголовком в title и массивом tags (минимум один тег). "
        "Для каждого тега поле article_type — только английский идентификатор "
        "(латинские буквы, цифры, подчёркивание; нижний регистр), например neuroscience, lab_safety. "
        "Поле article_name — короткая подпись тега на языке конспекта (как в параметре языка). "
        "Не пиши конспект только в свободном тексте без вызова функции."
    )
)
