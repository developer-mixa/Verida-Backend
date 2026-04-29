from __future__ import annotations

import io
import zipfile

import pytest
from httpx import AsyncClient


@pytest.mark.asyncio
async def test_import_zip_creates_folders_and_notes(
    async_client: AsyncClient,
    chat_auth_headers: dict[str, str],
) -> None:
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zf:
        zf.writestr("Транзакции/basics.md", "# Basics\nBody.")
        zf.writestr("root.md", "# Root only")
    buf.seek(0)

    res = await async_client.post(
        "/api/articles/import-zip",
        files={"file": ("conspects.zip", buf.getvalue(), "application/zip")},
        headers=chat_auth_headers,
    )
    assert res.status_code == 201, res.text
    data = res.json()
    assert data["created_count"] == 3
    assert len(data["root_article_ids"]) == 2

    roots = await async_client.get(
        "/api/articles",
        params={"roots_only": "true"},
        headers=chat_auth_headers,
    )
    assert roots.status_code == 200
    root_items = roots.json()
    assert len(root_items) == 2
    titles = {x["title"] for x in root_items}
    assert titles == {"Транзакции", "root"}
    folder = next(x for x in root_items if x["title"] == "Транзакции")
    assert folder["is_folder"] is True

    kids = await async_client.get(
        "/api/articles",
        params={"parent_id": folder["id"]},
        headers=chat_auth_headers,
    )
    assert kids.status_code == 200
    assert len(kids.json()) == 1
    assert kids.json()[0]["title"] == "basics"
    assert kids.json()[0]["is_folder"] is False


@pytest.mark.asyncio
async def test_import_zip_rejects_non_zip_content(
    async_client: AsyncClient,
    chat_auth_headers: dict[str, str],
) -> None:
    res = await async_client.post(
        "/api/articles/import-zip",
        files={"file": ("x.zip", b"not a zip", "application/zip")},
        headers=chat_auth_headers,
    )
    assert res.status_code == 400


@pytest.mark.asyncio
async def test_article_create_nested_folder(
    async_client: AsyncClient,
    chat_auth_headers: dict[str, str],
) -> None:
    folder = await async_client.post(
        "/api/articles",
        json={"title": "Раздел", "content": "", "tags": [], "is_folder": True},
        headers=chat_auth_headers,
    )
    assert folder.status_code == 201, folder.text
    fid = folder.json()["id"]
    assert folder.json()["is_folder"] is True

    note = await async_client.post(
        "/api/articles",
        json={
            "title": "Заметка",
            "content": "Текст",
            "tags": [],
            "parent_id": fid,
            "is_folder": False,
        },
        headers=chat_auth_headers,
    )
    assert note.status_code == 201
    assert note.json()["parent_id"] == fid

    listed = await async_client.get(
        "/api/articles",
        params={"parent_id": fid},
        headers=chat_auth_headers,
    )
    assert len(listed.json()) == 1
