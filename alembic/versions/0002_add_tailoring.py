"""add_tailoring_session_and_plan_item

Adds TailoringSession and PlanItem tables for the M2 LLM tailoring flow.

Revision ID: 0002_add_tailoring
Revises: 0001_m1_baseline
Create Date: 2026-05-01

"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "0002_add_tailoring"
down_revision: str | Sequence[str] | None = "0001_m1_baseline"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "tailoring_session",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("job_title", sa.String(length=200), nullable=False),
        sa.Column("company_name", sa.String(length=200), nullable=False),
        sa.Column("job_description", sa.Text(), nullable=False),
        sa.Column(
            "status",
            sa.Enum(
                "DRAFT",
                "ANALYZING",
                "ANALYZED",
                "PLAN_EDITED",
                "GENERATED",
                "EXPORTED",
                name="tailoringstatus",
            ),
            nullable=False,
        ),
        sa.Column("analysis_json", sa.JSON(), nullable=True),
        sa.Column("analysis_prompt_version", sa.String(length=16), nullable=True),
        sa.Column("generated_json", sa.JSON(), nullable=True),
        sa.Column("generation_prompt_version", sa.String(length=16), nullable=True),
        sa.Column("error_message", sa.Text(), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("(CURRENT_TIMESTAMP)"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("(CURRENT_TIMESTAMP)"),
            nullable=False,
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_table(
        "plan_item",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("session_id", sa.Integer(), nullable=False),
        sa.Column(
            "item_type",
            sa.Enum(
                "JOB",
                "ACHIEVEMENT",
                "SKILL_GROUP",
                "PROJECT",
                "EDUCATION",
                "CERTIFICATION",
                name="planitemtype",
            ),
            nullable=False,
        ),
        sa.Column("reference_id", sa.Integer(), nullable=True),
        sa.Column("include", sa.Boolean(), nullable=False),
        sa.Column("emphasis_note", sa.Text(), nullable=True),
        sa.Column("llm_rationale", sa.Text(), nullable=True),
        sa.Column("sort_order", sa.Integer(), nullable=False),
        sa.ForeignKeyConstraint(["session_id"], ["tailoring_session.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_plan_item_session_id", "plan_item", ["session_id"], unique=False)


def downgrade() -> None:
    op.drop_index("ix_plan_item_session_id", table_name="plan_item")
    op.drop_table("plan_item")
    op.drop_table("tailoring_session")
