"""add_education_location_expected

Adds location and expected_end_date columns to education table.

Revision ID: 0005_add_education_location_expected
Revises: 0004_add_cover_letter
Create Date: 2026-05-04

"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0005_add_education_location_expected"
down_revision: Union[str, Sequence[str], None] = "0004_add_cover_letter"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    with op.batch_alter_table("education") as batch_op:
        batch_op.add_column(sa.Column("location", sa.String(200), nullable=True))
        batch_op.add_column(sa.Column("expected_end_date", sa.Date(), nullable=True))


def downgrade() -> None:
    with op.batch_alter_table("education") as batch_op:
        batch_op.drop_column("expected_end_date")
        batch_op.drop_column("location")
