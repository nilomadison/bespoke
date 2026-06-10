"""add_cover_letter_columns

Adds cover_letter_json and cover_letter_generating columns to tailoring_session
for the M4 cover letter generation feature.

Revision ID: 0004_add_cover_letter
Revises: 0003_add_generating
Create Date: 2026-05-02

"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "0004_add_cover_letter"
down_revision: str | Sequence[str] | None = "0003_add_generating"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    with op.batch_alter_table("tailoring_session") as batch_op:
        batch_op.add_column(sa.Column("cover_letter_json", sa.JSON(), nullable=True))
        batch_op.add_column(
            sa.Column("cover_letter_generating", sa.Boolean(), nullable=False, server_default="0")
        )


def downgrade() -> None:
    with op.batch_alter_table("tailoring_session") as batch_op:
        batch_op.drop_column("cover_letter_generating")
        batch_op.drop_column("cover_letter_json")
