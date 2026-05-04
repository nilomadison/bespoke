"""add_generating_status

Adds GENERATING value to the tailoringstatus enum to track resume
generation in progress as a distinct state from analysis.

Revision ID: 0003_add_generating
Revises: 0002_add_tailoring
Create Date: 2026-05-02

"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0003_add_generating"
down_revision: Union[str, Sequence[str], None] = "0002_add_tailoring"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    with op.batch_alter_table("tailoring_session") as batch_op:
        batch_op.alter_column(
            "status",
            type_=sa.Enum(
                "DRAFT", "ANALYZING", "GENERATING", "ANALYZED", "PLAN_EDITED",
                "GENERATED", "EXPORTED",
                name="tailoringstatus",
            ),
            existing_type=sa.Enum(
                "DRAFT", "ANALYZING", "ANALYZED", "PLAN_EDITED",
                "GENERATED", "EXPORTED",
                name="tailoringstatus",
            ),
            existing_nullable=False,
        )


def downgrade() -> None:
    with op.batch_alter_table("tailoring_session") as batch_op:
        batch_op.alter_column(
            "status",
            type_=sa.Enum(
                "DRAFT", "ANALYZING", "ANALYZED", "PLAN_EDITED",
                "GENERATED", "EXPORTED",
                name="tailoringstatus",
            ),
            existing_type=sa.Enum(
                "DRAFT", "ANALYZING", "GENERATING", "ANALYZED", "PLAN_EDITED",
                "GENERATED", "EXPORTED",
                name="tailoringstatus",
            ),
            existing_nullable=False,
        )
