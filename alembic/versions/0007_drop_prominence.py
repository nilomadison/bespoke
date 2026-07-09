"""drop_prominence

Removes the prominence column from the achievement and project tables.
Prominence was a JD-blind pre-filter feeding only the planner LLM; ranking now
falls back to impact-signal overlap, recency, and concrete metrics.

Revision ID: 0007_drop_prominence
Revises: 0006_add_prompt_version_fields
Create Date: 2026-07-09

"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "0007_drop_prominence"
down_revision: str | Sequence[str] | None = "0006_add_prompt_version_fields"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    with op.batch_alter_table("achievement") as batch_op:
        batch_op.drop_column("prominence")
    with op.batch_alter_table("project") as batch_op:
        batch_op.drop_column("prominence")


def downgrade() -> None:
    with op.batch_alter_table("project") as batch_op:
        batch_op.add_column(
            sa.Column("prominence", sa.Integer(), nullable=False, server_default="3")
        )
    with op.batch_alter_table("achievement") as batch_op:
        batch_op.add_column(
            sa.Column("prominence", sa.Integer(), nullable=False, server_default="3")
        )
