from __future__ import annotations

import pytest
from httpx import AsyncClient


@pytest.mark.asyncio
async def test_create_chat_session(async_client: AsyncClient) -> None:
    r = await async_client.post("/api/chat/sessions", json={})
    assert r.status_code == 201
    data = r.json()
    assert "id" in data
    assert data["title"] == "Новая тема"
    assert "created_at" in data


@pytest.mark.asyncio
async def test_stream_message_unknown_session(async_client: AsyncClient) -> None:
    fake = "00000000-0000-4000-8000-000000000001"
    r = await async_client.post(
        f"/api/chat/sessions/{fake}/messages/stream",
        json={"content": "hello"},
    )
    assert r.status_code == 404


@pytest.mark.asyncio
async def test_stream_message_stub_sse(async_client: AsyncClient) -> None:
    sid = (await async_client.post("/api/chat/sessions", json={"title": "T"})).json()["id"]
    async with async_client.stream(
        "POST",
        f"/api/chat/sessions/{sid}/messages/stream",
        json={"content": "hello"},
    ) as resp:
        assert resp.status_code == 200
        assert resp.headers.get("content-type", "").startswith("text/event-stream")
        chunks = [c async for c in resp.aiter_bytes()]
    body = b"".join(chunks)
    assert b"delta" in body
    assert b"done" in body


@pytest.mark.asyncio
async def test_synopsis_not_implemented(async_client: AsyncClient) -> None:
    sid = (await async_client.post("/api/chat/sessions", json={})).json()["id"]
    r = await async_client.post(
        f"/api/chat/sessions/{sid}/synopsis",
        json={"language": "ru"},
    )
    assert r.status_code == 501
