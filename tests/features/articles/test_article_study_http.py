from __future__ import annotations

import random
import uuid
from unittest.mock import patch

import pytest
from httpx import AsyncClient

from app.features.articles.repositories.article_study_repository import ArticleStudyRepository


@pytest.mark.asyncio
async def test_questions_and_study_session_flow(
    async_client: AsyncClient,
    chat_auth_headers: dict[str, str],
) -> None:
    cr = await async_client.post(
        "/api/articles",
        json={"title": "T", "content": "C", "tags": []},
        headers=chat_auth_headers,
    )
    assert cr.status_code == 201, cr.text
    aid = cr.json()["id"]

    empty = await async_client.get(f"/api/articles/{aid}/questions", headers=chat_auth_headers)
    assert empty.status_code == 200
    assert empty.json() == []

    bad_start = await async_client.post(
        f"/api/articles/{aid}/study-sessions",
        headers=chat_auth_headers,
    )
    assert bad_start.status_code == 400

    q1 = await async_client.post(
        f"/api/articles/{aid}/questions",
        json={"question": "Q1", "answer": "A1"},
        headers=chat_auth_headers,
    )
    assert q1.status_code == 201, q1.text
    id1 = q1.json()["id"]
    q2 = await async_client.post(
        f"/api/articles/{aid}/questions",
        json={"question": "Q2", "answer": "A2"},
        headers=chat_auth_headers,
    )
    assert q2.status_code == 201
    id2 = q2.json()["id"]

    fixed_order = [uuid.UUID(id2), uuid.UUID(id1)]

    with patch.object(ArticleStudyRepository, "_weighted_deck_order", return_value=fixed_order):
        st = await async_client.post(
            f"/api/articles/{aid}/study-sessions",
            headers=chat_auth_headers,
        )
    assert st.status_code == 201, st.text
    body = st.json()
    sid = body["id"]
    assert body["deck_order"] == [str(id2), str(id1)]
    assert body["total_cards"] == 2
    assert body["correct_count"] == 0
    assert body["completed_at"] is None

    g = await async_client.get(
        f"/api/articles/{aid}/study-sessions/{sid}",
        headers=chat_auth_headers,
    )
    assert g.status_code == 200
    assert g.json()["deck_order"] == [str(id2), str(id1)]

    r1 = await async_client.post(
        f"/api/articles/{aid}/study-sessions/{sid}/reviews",
        headers=chat_auth_headers,
        json={"question_id": id2, "is_correct": True},
    )
    assert r1.status_code == 200, r1.text
    assert r1.json() == {
        "correct_count": 1,
        "total_cards": 2,
        "reviews_submitted": 1,
        "session_completed": False,
    }

    dup = await async_client.post(
        f"/api/articles/{aid}/study-sessions/{sid}/reviews",
        headers=chat_auth_headers,
        json={"question_id": id2, "is_correct": False},
    )
    assert dup.status_code == 409

    r2 = await async_client.post(
        f"/api/articles/{aid}/study-sessions/{sid}/reviews",
        headers=chat_auth_headers,
        json={"question_id": id1, "is_correct": False},
    )
    assert r2.status_code == 200
    assert r2.json()["session_completed"] is True
    assert r2.json()["reviews_submitted"] == 2
    assert r2.json()["correct_count"] == 1

    after = await async_client.post(
        f"/api/articles/{aid}/study-sessions/{sid}/reviews",
        headers=chat_auth_headers,
        json={"question_id": id1, "is_correct": True},
    )
    assert after.status_code == 409

    done = await async_client.get(
        f"/api/articles/{aid}/study-sessions/{sid}",
        headers=chat_auth_headers,
    )
    assert done.json()["completed_at"] is not None


@pytest.mark.asyncio
async def test_article_questions_not_owned_404(
    async_client: AsyncClient,
    chat_auth_headers: dict[str, str],
) -> None:
    other = uuid.uuid4()
    r = await async_client.get(f"/api/articles/{other}/questions", headers=chat_auth_headers)
    assert r.status_code == 404


@pytest.mark.asyncio
async def test_weighted_order_prefers_more_wrongs(
    async_client: AsyncClient,
    chat_auth_headers: dict[str, str],
) -> None:
    cr = await async_client.post(
        "/api/articles",
        json={"title": "W", "content": "X", "tags": []},
        headers=chat_auth_headers,
    )
    aid = cr.json()["id"]
    qa = []
    for i in range(3):
        q = await async_client.post(
            f"/api/articles/{aid}/questions",
            json={"question": f"q{i}", "answer": f"a{i}"},
            headers=chat_auth_headers,
        )
        assert q.status_code == 201
        qa.append(q.json()["id"])
    id0, id1, id2 = [uuid.UUID(x) for x in qa]

    rng = random.Random(42)
    deck1 = ArticleStudyRepository._weighted_deck_order([id0, id1, id2], {}, rng=rng)
    assert sorted(deck1) == sorted([id0, id1, id2])

    wrong_map = {id1: 5, id0: 0, id2: 1}
    rng2 = random.Random(0)
    decks = [ArticleStudyRepository._weighted_deck_order([id0, id1, id2], wrong_map, rng=rng2) for _ in range(200)]
    first_positions = [d.index(id1) for d in decks]
    assert min(first_positions) == 0
    assert sum(1 for p in first_positions if p == 0) >= 120
