"""Сессии вопрос–ответ по статье и журнал самооценок (для весовой выдачи).

Revision ID: 0005_article_study_reviews
Revises: 0004_ai_chat_tables
Create Date: 2026-04-21

"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0005_article_study_reviews"
down_revision: Union[str, None] = "0004_ai_chat_tables"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "article_study_sessions",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("user_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("article_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("deck_order", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("total_cards", sa.Integer(), nullable=False),
        sa.Column("correct_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], name="fk_article_study_sessions_user_id_users", ondelete="CASCADE"),
        sa.ForeignKeyConstraint(
            ["article_id"],
            ["articles.id"],
            name="fk_article_study_sessions_article_id_articles",
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name="pk_article_study_sessions"),
    )
    op.create_index(
        "ix_article_study_sessions_user_article_created",
        "article_study_sessions",
        ["user_id", "article_id", "created_at"],
    )

    op.create_table(
        "article_question_reviews",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("user_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("question_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("study_session_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("is_correct", sa.Boolean(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(
            ["user_id"],
            ["users.id"],
            name="fk_article_question_reviews_user_id_users",
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["question_id"],
            ["article_questions.id"],
            name="fk_article_question_reviews_question_id_article_questions",
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["study_session_id"],
            ["article_study_sessions.id"],
            name="fk_article_question_reviews_study_session_id_sessions",
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name="pk_article_question_reviews"),
        sa.UniqueConstraint(
            "study_session_id",
            "question_id",
            name="uq_article_question_reviews_session_question",
        ),
    )
    op.create_index(
        "ix_article_question_reviews_user_question",
        "article_question_reviews",
        ["user_id", "question_id"],
    )
    op.create_index(
        "ix_article_question_reviews_session",
        "article_question_reviews",
        ["study_session_id"],
    )


def downgrade() -> None:
    op.drop_index("ix_article_question_reviews_session", table_name="article_question_reviews")
    op.drop_index("ix_article_question_reviews_user_question", table_name="article_question_reviews")
    op.drop_table("article_question_reviews")
    op.drop_index("ix_article_study_sessions_user_article_created", table_name="article_study_sessions")
    op.drop_table("article_study_sessions")
