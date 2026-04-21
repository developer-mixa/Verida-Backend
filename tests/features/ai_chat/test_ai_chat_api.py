from __future__ import annotations

import uuid

import pytest
from httpx import AsyncClient


@pytest.mark.asyncio
async def test_chat_sessions_require_auth(async_client: AsyncClient) -> None:
    r = await async_client.post("/api/chat/sessions", json={})
    assert r.status_code == 401


@pytest.mark.asyncio
async def test_create_chat_session(async_client: AsyncClient, chat_auth_headers: dict[str, str]) -> None:
    r = await async_client.post("/api/chat/sessions", json={}, headers=chat_auth_headers)
    assert r.status_code == 201
    data = r.json()
    assert "id" in data
    assert data["title"] == "Новая тема"
    assert "created_at" in data


@pytest.mark.asyncio
async def test_stream_message_unknown_session(
    async_client: AsyncClient,
    chat_auth_headers: dict[str, str],
) -> None:
    fake = "00000000-0000-4000-8000-000000000001"
    r = await async_client.post(
        f"/api/chat/sessions/{fake}/messages/stream",
        json={"content": "hello"},
        headers=chat_auth_headers,
    )
    assert r.status_code == 404


@pytest.mark.asyncio
async def test_stream_message_sse(async_client: AsyncClient, chat_auth_headers: dict[str, str]) -> None:
    sid = (
        await async_client.post("/api/chat/sessions", json={"title": "T"}, headers=chat_auth_headers)
    ).json()["id"]
    async with async_client.stream(
        "POST",
        f"/api/chat/sessions/{sid}/messages/stream",
        json={"content": "hello"},
        headers=chat_auth_headers,
    ) as resp:
        assert resp.status_code == 200
        assert resp.headers.get("content-type", "").startswith("text/event-stream")
        chunks = [c async for c in resp.aiter_bytes()]
    body = b"".join(chunks)
    assert b"delta" in body
    assert b"done" in body


@pytest.mark.asyncio
async def test_synopsis_creates_article(
    async_client: AsyncClient,
    chat_auth_headers: dict[str, str],
) -> None:
    sid = (await async_client.post("/api/chat/sessions", json={}, headers=chat_auth_headers)).json()["id"]
    async with async_client.stream(
        "POST",
        f"/api/chat/sessions/{sid}/messages/stream",
        json={"content": "сообщение пользователя"},
        headers=chat_auth_headers,
    ) as resp:
        assert resp.status_code == 200
        _ = [c async for c in resp.aiter_bytes()]

    r = await async_client.post(
        f"/api/chat/sessions/{sid}/synopsis",
        json={"language": "ru"},
        headers=chat_auth_headers,
    )
    assert r.status_code == 200, r.text
    data = r.json()
    assert data["updated"] is False
    assert data["title"] == "Конспект"
    assert uuid.UUID(data["article_id"])
    assert len(data["tags"]) == 2
    types = {t["article_type"] for t in data["tags"]}
    assert types == {"biology", "methodology"}


@pytest.mark.asyncio
async def test_synopsis_updates_existing_article(
    async_client: AsyncClient,
    chat_auth_headers: dict[str, str],
) -> None:
    sid = (await async_client.post("/api/chat/sessions", json={}, headers=chat_auth_headers)).json()["id"]
    async with async_client.stream(
        "POST",
        f"/api/chat/sessions/{sid}/messages/stream",
        json={"content": "x"},
        headers=chat_auth_headers,
    ) as resp:
        assert resp.status_code == 200
        _ = [c async for c in resp.aiter_bytes()]

    r1 = await async_client.post(
        f"/api/chat/sessions/{sid}/synopsis",
        json={"language": "ru"},
        headers=chat_auth_headers,
    )
    assert r1.status_code == 200
    aid = r1.json()["article_id"]

    r2 = await async_client.post(
        f"/api/chat/sessions/{sid}/synopsis",
        json={"language": "ru"},
        headers=chat_auth_headers,
    )
    assert r2.status_code == 200
    assert r2.json()["updated"] is True
    assert r2.json()["article_id"] == aid


@pytest.mark.asyncio
async def test_synopsis_empty_thread(
    async_client: AsyncClient,
    chat_auth_headers: dict[str, str],
) -> None:
    sid = (await async_client.post("/api/chat/sessions", json={}, headers=chat_auth_headers)).json()["id"]
    r = await async_client.post(
        f"/api/chat/sessions/{sid}/synopsis",
        json={"language": "ru"},
        headers=chat_auth_headers,
    )
    assert r.status_code == 422
