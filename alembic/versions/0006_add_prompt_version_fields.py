"""add_prompt_version_fields

Adds plan_prompt_version and cover_letter_prompt_version to tailoring_session,
so all four LLM stages (analyze, plan, generate, cover letter) record the hash
of the prompt that produced their output.

Revision ID: 0006_add_prompt_version_fields
Revises: 0005_add_education_location_expected
Create Date: 2026-06-10

"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "0006_add_prompt_version_fields"
down_revision: str | Sequence[str] | None = "0005_add_education_location_expected"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    with op.batch_alter_table("tailoring_session") as batch_op:
        batch_op.add_column(sa.Column("plan_prompt_version", sa.String(16), nullable=True))
        batch_op.add_column(sa.Column("cover_letter_prompt_version", sa.String(16), nullable=True))


def downgrade() -> None:
    with op.batch_alter_table("tailoring_session") as batch_op:
        batch_op.drop_column("cover_letter_prompt_version")
        batch_op.drop_column("plan_prompt_version")
