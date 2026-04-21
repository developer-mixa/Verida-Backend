from __future__ import annotations

import uuid

import pytest
from httpx import AsyncClient

from app.features.ai_chat.deps import get_chat_llm
from app.main import app


class _FakeChatLlm:
    async def stream_reply(self, *, messages: list[dict[str, str]]):
        yield "Ответ "
        yield "модели."

    async def synopsis_save_args(self, *, dialogue_block: str, language: str | None) -> dict:
        _ = dialogue_block, language
        return {
            "title": "Конспект",
            "content": "## Итог\nТекст конспекта.",
            "tags": [
                {"article_type": "biology", "article_name": "Клетки"},
                {"article_type": "methodology", "article_name": "Метод"},
            ],
        }


@pytest.fixture(autouse=True)
def _override_chat_llm() -> None:
    app.dependency_overrides[get_chat_llm] = lambda: _FakeChatLlm()
    yield
    app.dependency_overrides.pop(get_chat_llm, None)


@pytest.fixture
async def chat_auth_headers(async_client: AsyncClient) -> dict[str, str]:
    username = f"ch{uuid.uuid4().hex[:10]}"
    reg = await async_client.post(
        "/api/auth/register",
        json={
            "username": username,
            "email": f"{username}@test.example",
            "password": "password1",
        },
    )
    assert reg.status_code == 201, reg.text
    token = reg.json()["access_token"]
    return {"Authorization": f"Bearer {token}"}
