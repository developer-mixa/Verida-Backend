import pytest
from httpx import AsyncClient


@pytest.mark.asyncio
async def test_register_login_with_email(async_client: AsyncClient) -> None:
    reg = await async_client.post(
        "/api/auth/register",
        json={
            "username": "alice",
            "email": "Alice@Example.com",
            "phone": None,
            "password": "password1",
        },
    )
    assert reg.status_code == 201, reg.text
    assert reg.json()["token_type"] == "bearer"
    assert reg.json()["access_token"]

    login = await async_client.post(
        "/api/auth/login",
        json={"contact": "alice", "password": "password1"},
    )
    assert login.status_code == 200, login.text

    login_email = await async_client.post(
        "/api/auth/login",
        json={"contact": "alice@example.com", "password": "password1"},
    )
    assert login_email.status_code == 200


@pytest.mark.asyncio
async def test_register_login_with_phone(async_client: AsyncClient) -> None:
    reg = await async_client.post(
        "/api/auth/register",
        json={
            "username": "bob",
            "email": None,
            "phone": "+7 999 111-22-33",
            "password": "password1",
        },
    )
    assert reg.status_code == 201, reg.text

    login = await async_client.post(
        "/api/auth/login",
        json={"contact": "+79991112233", "password": "password1"},
    )
    assert login.status_code == 200


@pytest.mark.asyncio
async def test_register_duplicate_username(async_client: AsyncClient) -> None:
    body = {
        "username": "dup",
        "email": "d1@e.co",
        "phone": None,
        "password": "password1",
    }
    r1 = await async_client.post("/api/auth/register", json=body)
    assert r1.status_code == 201
    r2 = await async_client.post(
        "/api/auth/register",
        json={**body, "email": "d2@e.co"},
    )
    assert r2.status_code == 409


@pytest.mark.asyncio
async def test_login_wrong_password(async_client: AsyncClient) -> None:
    await async_client.post(
        "/api/auth/register",
        json={
            "username": "carl",
            "email": "carl@e.co",
            "password": "password1",
        },
    )
    bad = await async_client.post(
        "/api/auth/login",
        json={"contact": "carl", "password": "wrong"},
    )
    assert bad.status_code == 401
