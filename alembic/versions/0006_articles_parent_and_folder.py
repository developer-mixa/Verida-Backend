"""Иерархия статей: родитель и признак папки (импорт / Obsidian-подобное дерево).

Revision ID: 0006_articles_parent_and_folder
Revises: 0005_article_study_reviews
Create Date: 2026-04-29

"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0006_articles_parent_and_folder"
down_revision: Union[str, None] = "0005_article_study_reviews"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "articles",
        sa.Column("parent_id", postgresql.UUID(as_uuid=True), nullable=True),
    )
    op.add_column(
        "articles",
        sa.Column("is_folder", sa.Boolean(), server_default=sa.text("false"), nullable=False),
    )
    op.create_foreign_key(
        "fk_articles_parent_id_articles",
        "articles",
        "articles",
        ["parent_id"],
        ["id"],
        ondelete="CASCADE",
    )
    op.create_index("ix_articles_user_id_parent_id", "articles", ["user_id", "parent_id"])


def downgrade() -> None:
    op.drop_index("ix_articles_user_id_parent_id", table_name="articles")
    op.drop_constraint("fk_articles_parent_id_articles", "articles", type_="foreignkey")
    op.drop_column("articles", "is_folder")
    op.drop_column("articles", "parent_id")
