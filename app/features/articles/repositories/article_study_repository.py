from __future__ import annotations

import random
import uuid
from dataclasses import dataclass
from typing import Literal

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.models.article import Article
from app.core.models.article_question import ArticleQuestion
from app.core.models.article_question_review import ArticleQuestionReview
from app.core.models.article_study_session import ArticleStudySession


@dataclass(frozen=True)
class StudyReviewResult:
    correct_count: int
    total_cards: int
    reviews_submitted: int
    session_completed: bool


class ArticleStudyRepository:
    def __init__(self, db: AsyncSession) -> None:
        self._db = db

    async def _article_owned(self, *, article_id: uuid.UUID, user_id: uuid.UUID) -> Article | None:
        r = await self._db.execute(
            select(Article).where(Article.id == article_id, Article.user_id == user_id)
        )
        return r.scalar_one_or_none()

    async def list_questions(
        self,
        *,
        article_id: uuid.UUID,
        user_id: uuid.UUID,
    ) -> list[ArticleQuestion] | None:
        if await self._article_owned(article_id=article_id, user_id=user_id) is None:
            return None
        r = await self._db.execute(
            select(ArticleQuestion)
            .where(ArticleQuestion.article_id == article_id)
            .order_by(ArticleQuestion.id)
        )
        return list(r.scalars().all())

    async def _get_question_owned(
        self,
        *,
        article_id: uuid.UUID,
        user_id: uuid.UUID,
        question_id: uuid.UUID,
    ) -> ArticleQuestion | None:
        r = await self._db.execute(
            select(ArticleQuestion)
            .join(Article, Article.id == ArticleQuestion.article_id)
            .where(
                ArticleQuestion.id == question_id,
                ArticleQuestion.article_id == article_id,
                Article.user_id == user_id,
            )
        )
        return r.scalar_one_or_none()

    async def create_question(
        self,
        *,
        article_id: uuid.UUID,
        user_id: uuid.UUID,
        question: str,
        answer: str,
    ) -> ArticleQuestion | None:
        if await self._article_owned(article_id=article_id, user_id=user_id) is None:
            return None
        row = ArticleQuestion(article_id=article_id, question=question, answer=answer)
        self._db.add(row)
        await self._db.flush()
        return row

    async def update_question(
        self,
        *,
        article_id: uuid.UUID,
        user_id: uuid.UUID,
        question_id: uuid.UUID,
        question: str | None,
        answer: str | None,
    ) -> ArticleQuestion | None:
        row = await self._get_question_owned(
            article_id=article_id, user_id=user_id, question_id=question_id
        )
        if row is None:
            return None
        if question is not None:
            row.question = question
        if answer is not None:
            row.answer = answer
        await self._db.flush()
        return row

    async def delete_question(
        self,
        *,
        article_id: uuid.UUID,
        user_id: uuid.UUID,
        question_id: uuid.UUID,
    ) -> bool:
        row = await self._get_question_owned(
            article_id=article_id, user_id=user_id, question_id=question_id
        )
        if row is None:
            return False
        await self._db.delete(row)
        await self._db.flush()
        return True

    async def _wrong_answer_counts(
        self,
        *,
        user_id: uuid.UUID,
        question_ids: list[uuid.UUID],
    ) -> dict[uuid.UUID, int]:
        if not question_ids:
            return {}
        r = await self._db.execute(
            select(ArticleQuestionReview.question_id, func.count())
            .where(
                ArticleQuestionReview.user_id == user_id,
                ArticleQuestionReview.question_id.in_(question_ids),
                ArticleQuestionReview.is_correct.is_(False),
            )
            .group_by(ArticleQuestionReview.question_id)
        )
        return {row[0]: int(row[1]) for row in r.all()}

    @staticmethod
    def _weighted_deck_order(
        question_ids: list[uuid.UUID],
        wrong_counts: dict[uuid.UUID, int],
        rng: random.Random | None = None,
    ) -> list[uuid.UUID]:
        rng = rng or random.Random()
        remaining: dict[uuid.UUID, int] = {
            qid: 1 + int(wrong_counts.get(qid, 0)) for qid in question_ids
        }
        deck: list[uuid.UUID] = []
        while remaining:
            keys = list(remaining.keys())
            weights = [remaining[k] for k in keys]
            pick = rng.choices(keys, weights=weights, k=1)[0]
            deck.append(pick)
            del remaining[pick]
        return deck

    async def start_study_session(
        self,
        *,
        article_id: uuid.UUID,
        user_id: uuid.UUID,
        rng: random.Random | None = None,
    ) -> ArticleStudySession | Literal["not_owned", "empty"]:
        if await self._article_owned(article_id=article_id, user_id=user_id) is None:
            return "not_owned"
        r = await self._db.execute(
            select(ArticleQuestion.id).where(ArticleQuestion.article_id == article_id)
        )
        qids = list(r.scalars().all())
        if not qids:
            return "empty"
        wrong = await self._wrong_answer_counts(user_id=user_id, question_ids=qids)
        deck = self._weighted_deck_order(qids, wrong, rng=rng)
        sess = ArticleStudySession(
            user_id=user_id,
            article_id=article_id,
            deck_order=[str(x) for x in deck],
            total_cards=len(deck),
            correct_count=0,
        )
        self._db.add(sess)
        await self._db.flush()
        return sess

    async def get_study_session(
        self,
        *,
        article_id: uuid.UUID,
        user_id: uuid.UUID,
        session_id: uuid.UUID,
    ) -> ArticleStudySession | None:
        r = await self._db.execute(
            select(ArticleStudySession).where(
                ArticleStudySession.id == session_id,
                ArticleStudySession.user_id == user_id,
                ArticleStudySession.article_id == article_id,
            )
        )
        return r.scalar_one_or_none()

    async def submit_study_review(
        self,
        *,
        article_id: uuid.UUID,
        user_id: uuid.UUID,
        session_id: uuid.UUID,
        question_id: uuid.UUID,
        is_correct: bool,
    ) -> (
        StudyReviewResult
        | Literal["session_not_found", "already_completed", "bad_question", "duplicate"]
    ):
        sess = await self.get_study_session(
            article_id=article_id, user_id=user_id, session_id=session_id
        )
        if sess is None:
            return "session_not_found"
        if sess.completed_at is not None:
            return "already_completed"
        if str(question_id) not in sess.deck_order:
            return "bad_question"
        q = await self._get_question_owned(
            article_id=article_id, user_id=user_id, question_id=question_id
        )
        if q is None:
            return "bad_question"
        dup = await self._db.scalar(
            select(func.count())
            .select_from(ArticleQuestionReview)
            .where(
                ArticleQuestionReview.study_session_id == session_id,
                ArticleQuestionReview.question_id == question_id,
            )
        )
        if dup and int(dup) > 0:
            return "duplicate"
        self._db.add(
            ArticleQuestionReview(
                user_id=user_id,
                question_id=question_id,
                study_session_id=session_id,
                is_correct=is_correct,
            )
        )
        if is_correct:
            sess.correct_count += 1
        await self._db.flush()
        reviews_submitted = int(
            await self._db.scalar(
                select(func.count())
                .select_from(ArticleQuestionReview)
                .where(ArticleQuestionReview.study_session_id == session_id)
            )
            or 0
        )
        if reviews_submitted >= sess.total_cards:
            from datetime import datetime, timezone

            sess.completed_at = datetime.now(timezone.utc)
            await self._db.flush()
        return StudyReviewResult(
            correct_count=sess.correct_count,
            total_cards=sess.total_cards,
            reviews_submitted=reviews_submitted,
            session_completed=sess.completed_at is not None,
        )
