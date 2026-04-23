from __future__ import annotations

import uuid

import pytest
from httpx import AsyncClient


@pytest.mark.asyncio
async def test_article_create_update_delete(
    async_client: AsyncClient,
    chat_auth_headers: dict[str, str],
) -> None:
    cr = await async_client.post(
        "/api/articles",
        json={
            "title": "  Моя заметка  ",
            "content": "# Текст\nПараграф.",
            "tags": [
                {"article_type": "note", "article_name": "Личное"},
                {"article_type": "idea", "article_name": "Идея"},
            ],
        },
        headers=chat_auth_headers,
    )
    assert cr.status_code == 201, cr.text
    body = cr.json()
    aid = body["id"]
    assert body["title"] == "Моя заметка"
    assert body["content"] == "# Текст\nПараграф."
    assert len(body["tags"]) == 2

    up = await async_client.patch(
        f"/api/articles/{aid}",
        json={"title": "Обновлено", "tags": [{"article_type": "note", "article_name": "Одно"}]},
        headers=chat_auth_headers,
    )
    assert up.status_code == 200, up.text
    assert up.json()["title"] == "Обновлено"
    assert len(up.json()["tags"]) == 1

    de = await async_client.delete(f"/api/articles/{aid}", headers=chat_auth_headers)
    assert de.status_code == 204

    g = await async_client.get(f"/api/articles/{aid}", headers=chat_auth_headers)
    assert g.status_code == 404


@pytest.mark.asyncio
async def test_article_create_bad_chat_session(
    async_client: AsyncClient,
    chat_auth_headers: dict[str, str],
) -> None:
    bad = uuid.uuid4()
    cr = await async_client.post(
        "/api/articles",
        json={
            "title": "X",
            "content": "Y",
            "tags": [],
            "chat_session_id": str(bad),
        },
        headers=chat_auth_headers,
    )
    assert cr.status_code == 400


@pytest.mark.asyncio
async def test_article_patch_requires_field(
    async_client: AsyncClient,
    chat_auth_headers: dict[str, str],
) -> None:
    cr = await async_client.post(
        "/api/articles",
        json={"title": "T", "content": "C", "tags": []},
        headers=chat_auth_headers,
    )
    assert cr.status_code == 201
    aid = cr.json()["id"]
    bad = await async_client.patch(f"/api/articles/{aid}", json={}, headers=chat_auth_headers)
    assert bad.status_code == 422
