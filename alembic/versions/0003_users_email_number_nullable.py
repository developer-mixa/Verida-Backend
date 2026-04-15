"""email и number опциональны; хотя бы одно обязательно (CHECK).

Revision ID: 0003_users_email_number_nullable
Revises: 0002_schema_domain
Create Date: 2026-04-15

"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0003_users_email_number_nullable"
down_revision: Union[str, None] = "0002_schema_domain"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.alter_column("users", "email", existing_type=sa.String(length=320), nullable=True)
    op.alter_column("users", "number", existing_type=sa.String(length=32), nullable=True)
    op.create_check_constraint(
        "ck_users_email_or_number_present",
        "users",
        sa.text("email IS NOT NULL OR number IS NOT NULL"),
    )


def downgrade() -> None:
    op.drop_constraint("ck_users_email_or_number_present", "users", type_="check")
    op.execute(
        sa.text(
            "UPDATE users SET email = '' WHERE email IS NULL; "
            "UPDATE users SET number = '' WHERE number IS NULL;"
        )
    )
    op.alter_column("users", "email", existing_type=sa.String(length=320), nullable=False)
    op.alter_column("users", "number", existing_type=sa.String(length=32), nullable=False)
