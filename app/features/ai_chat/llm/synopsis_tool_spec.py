from __future__ import annotations

from typing import Any

# Один системный промпт: правила конспекта + обязательный вызов save_synopsis (как instructions в test-project).
SYNOPSIS_INSTRUCTIONS = (
    "Ты составляешь конспект переписки. Опирайся только на текст переписки, который пользователь присылает ниже; "
    "не добавляй факты и цитаты, которых нет в этом тексте. "
    "Заверши задачу одним вызовом инструмента save_synopsis: не отвечай свободным текстом и не выдавай JSON в сообщении. "
    "В save_synopsis: title — короткий заголовок без markdown; content — полный конспект в Markdown; "
    "tags — от одного до восьми тегов: article_type только латиницей в нижнем регистре (например science, history), "
    "article_name — короткая подпись на языке конспекта. Аргументы инструмента — валидный JSON по схеме, без обёрток ```."
)

# Плоский function tool в том же стиле, что log_exercise в test-project (без strict / additionalProperties).
SAVE_SYNOPSIS_RESPONSES_TOOL: dict[str, Any] = {
    "type": "function",
    "name": "save_synopsis",
    "description": "Вызывай, когда нужно сохранить конспект переписки: один раз передай title, полный content (Markdown) и tags.",
    "parameters": {
        "type": "object",
        "properties": {
            "title": {
                "type": "string",
                "description": "Краткий заголовок конспекта, без markdown и лишних кавычек.",
            },
            "content": {
                "type": "string",
                "description": "Полный текст конспекта в Markdown.",
            },
            "tags": {
                "type": "array",
                "description": "Теги темы (1–8 штук): article_type — ключ на латинице, article_name — подпись.",
                "items": {
                    "type": "object",
                    "properties": {
                        "article_type": {
                            "type": "string",
                            "description": "English-only ключ, например science, history, psychology.",
                        },
                        "article_name": {
                            "type": "string",
                            "description": "Отображаемое имя тега на языке конспекта.",
                        },
                    },
                    "required": ["article_type", "article_name"],
                },
            },
        },
        "required": ["title", "content", "tags"],
    },
}

# Обратная совместимость имён (если где-то импортировали старое имя).
SYSTEM_SYNOPSIS = SYNOPSIS_INSTRUCTIONS
