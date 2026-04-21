from __future__ import annotations

import uuid

import pytest
from httpx import AsyncClient


@pytest.mark.asyncio
async def test_articles_list_requires_auth(async_client: AsyncClient) -> None:
    r = await async_client.get("/api/articles")
    assert r.status_code == 401


@pytest.mark.asyncio
async def test_articles_list_and_detail_after_synopsis(
    async_client: AsyncClient,
    chat_auth_headers: dict[str, str],
) -> None:
    sid = (
        await async_client.post("/api/chat/sessions", json={"title": "T"}, headers=chat_auth_headers)
    ).json()["id"]
    await async_client.post(
        f"/api/chat/sessions/{sid}/messages/stream",
        json={"content": "сообщение для конспекта"},
        headers=chat_auth_headers,
    )
    syn = await async_client.post(
        f"/api/chat/sessions/{sid}/synopsis",
        json={"language": "ru"},
        headers=chat_auth_headers,
    )
    assert syn.status_code == 200, syn.text
    aid = syn.json()["article_id"]

    lst = await async_client.get("/api/articles", headers=chat_auth_headers)
    assert lst.status_code == 200
    items = lst.json()
    assert len(items) >= 1
    found = next((x for x in items if x["id"] == str(aid)), None)
    assert found is not None
    assert found["title"]
    assert "tags" in found

    det = await async_client.get(f"/api/articles/{aid}", headers=chat_auth_headers)
    assert det.status_code == 200
    body = det.json()
    assert body["id"] == str(aid)
    assert body["content"]
    assert isinstance(body["tags"], list)


@pytest.mark.asyncio
async def test_article_detail_404_other_user(
    async_client: AsyncClient,
    chat_auth_headers: dict[str, str],
) -> None:
    sid = (
        await async_client.post("/api/chat/sessions", json={}, headers=chat_auth_headers)
    ).json()["id"]
    await async_client.post(
        f"/api/chat/sessions/{sid}/messages/stream",
        json={"content": "x"},
        headers=chat_auth_headers,
    )
    syn = await async_client.post(
        f"/api/chat/sessions/{sid}/synopsis",
        json={},
        headers=chat_auth_headers,
    )
    assert syn.status_code == 200
    aid = syn.json()["article_id"]

    u2 = f"u2{uuid.uuid4().hex[:10]}"
    reg2 = await async_client.post(
        "/api/auth/register",
        json={"username": u2, "email": f"{u2}@t.example", "password": "password1"},
    )
    assert reg2.status_code == 201
    h2 = {"Authorization": f"Bearer {reg2.json()['access_token']}"}

    r = await async_client.get(f"/api/articles/{aid}", headers=h2)
    assert r.status_code == 404
