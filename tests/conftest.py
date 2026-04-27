from __future__ import annotations

from collections.abc import AsyncIterator

import pytest_asyncio

pytest_plugins = ["tests.features.ai_chat.conftest"]
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.pool import StaticPool

from app.core.database import Base, get_db
import app.core.models  # noqa: F401 — все таблицы в metadata для create_all в тестах
from app.core.models import Role
from app.core.constants import ROLE_USER_ID
from app.main import app

import app.core.database as db_module
import app.features.ai_chat.router as ai_chat_router_module


@pytest_asyncio.fixture
async def async_client() -> AsyncIterator[AsyncClient]:
    engine = create_async_engine(
        "sqlite+aiosqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    session_factory = async_sessionmaker(engine, expire_on_commit=False, class_=AsyncSession)

    _orig_db_session_local = db_module.AsyncSessionLocal
    _orig_router_session_local = ai_chat_router_module.AsyncSessionLocal
    db_module.AsyncSessionLocal = session_factory
    ai_chat_router_module.AsyncSessionLocal = session_factory

    async with session_factory() as session:
        session.add(Role(id=ROLE_USER_ID, name="user"))
        await session.commit()

    async def _override_get_db() -> AsyncIterator[AsyncSession]:
        async with session_factory() as session:
            yield session

    app.dependency_overrides[get_db] = _override_get_db
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        yield client

    app.dependency_overrides.clear()
    db_module.AsyncSessionLocal = _orig_db_session_local
    ai_chat_router_module.AsyncSessionLocal = _orig_router_session_local
    await engine.dispose()
