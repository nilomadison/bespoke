"""baseline

Consolidated full-schema baseline. This single revision replaces the former
incremental history (0001_m1_baseline .. 0007_drop_prominence), which was
squashed once the app had no other databases at an intermediate revision.

It creates the entire current schema, so `alembic upgrade head` builds a blank
database from scratch. `init_db()` still calls `create_all()` for the dev/test
flow; the two are kept in lockstep (a schema change requires a new migration).

Revision ID: 0001_baseline
Revises:
Create Date: 2026-07-09

"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "0001_baseline"
down_revision: str | Sequence[str] | None = None
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "certification",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("name", sa.String(length=200), nullable=False),
        sa.Column("issuer", sa.String(length=200), nullable=False),
        sa.Column("issue_date", sa.Date(), nullable=True),
        sa.Column("expiry_date", sa.Date(), nullable=True),
        sa.Column("credential_id", sa.String(length=200), nullable=True),
        sa.Column("credential_url", sa.String(length=500), nullable=True),
        sa.Column("notes", sa.Text(), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_table(
        "education",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("institution", sa.String(length=200), nullable=False),
        sa.Column("degree", sa.String(length=200), nullable=False),
        sa.Column("field", sa.String(length=200), nullable=False),
        sa.Column("location", sa.String(length=200), nullable=True),
        sa.Column("start_date", sa.Date(), nullable=True),
        sa.Column("end_date", sa.Date(), nullable=True),
        sa.Column("expected_end_date", sa.Date(), nullable=True),
        sa.Column("is_in_progress", sa.Boolean(), nullable=False),
        sa.Column("gpa", sa.Float(), nullable=True),
        sa.Column("honors", sa.String(length=500), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_table(
        "job",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("title", sa.String(length=200), nullable=False),
        sa.Column("company", sa.String(length=200), nullable=False),
        sa.Column("location", sa.String(length=200), nullable=True),
        sa.Column("start_date", sa.Date(), nullable=False),
        sa.Column("end_date", sa.Date(), nullable=True),
        sa.Column(
            "employment_type",
            sa.Enum(
                "FULL_TIME",
                "PART_TIME",
                "CONTRACT",
                "FREELANCE",
                "INTERNSHIP",
                "CO_FOUNDER",
                name="employmenttype",
            ),
            nullable=False,
        ),
        sa.Column("summary", sa.Text(), nullable=True),
        sa.Column("is_technical", sa.Boolean(), nullable=False),
        sa.Column("sort_order", sa.Integer(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_table(
        "profile",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("full_name", sa.String(length=200), nullable=False),
        sa.Column("email", sa.String(length=200), nullable=False),
        sa.Column("phone", sa.String(length=50), nullable=True),
        sa.Column("location", sa.String(length=200), nullable=True),
        sa.Column("linkedin_url", sa.String(length=500), nullable=True),
        sa.Column("github_url", sa.String(length=500), nullable=True),
        sa.Column("portfolio_url", sa.String(length=500), nullable=True),
        sa.Column("baseline_summary", sa.Text(), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_table(
        "skill",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("name", sa.String(length=100), nullable=False),
        sa.Column("category", sa.String(length=100), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("name"),
    )
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
                "GENERATING",
                "GENERATED",
                "EXPORTED",
                name="tailoringstatus",
            ),
            nullable=False,
        ),
        sa.Column("analysis_json", sa.JSON(), nullable=True),
        sa.Column("analysis_prompt_version", sa.String(length=16), nullable=True),
        sa.Column("plan_prompt_version", sa.String(length=16), nullable=True),
        sa.Column("generated_json", sa.JSON(), nullable=True),
        sa.Column("generation_prompt_version", sa.String(length=16), nullable=True),
        sa.Column("cover_letter_json", sa.JSON(), nullable=True),
        sa.Column("cover_letter_generating", sa.Boolean(), nullable=False),
        sa.Column("cover_letter_prompt_version", sa.String(length=16), nullable=True),
        sa.Column("error_message", sa.Text(), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_table(
        "achievement",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("job_id", sa.Integer(), nullable=False),
        sa.Column("text", sa.Text(), nullable=False),
        sa.Column("metric", sa.String(length=500), nullable=True),
        sa.Column("impact_tags", sa.JSON(), nullable=False),
        sa.Column("sort_order", sa.Integer(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(["job_id"], ["job.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    with op.batch_alter_table("achievement", schema=None) as batch_op:
        batch_op.create_index(batch_op.f("ix_achievement_job_id"), ["job_id"], unique=False)

    op.create_table(
        "job_skill",
        sa.Column("job_id", sa.Integer(), nullable=False),
        sa.Column("skill_id", sa.Integer(), nullable=False),
        sa.Column("proficiency", sa.String(length=50), nullable=True),
        sa.Column("years_used", sa.Float(), nullable=True),
        sa.ForeignKeyConstraint(["job_id"], ["job.id"]),
        sa.ForeignKeyConstraint(["skill_id"], ["skill.id"]),
        sa.PrimaryKeyConstraint("job_id", "skill_id"),
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
    with op.batch_alter_table("plan_item", schema=None) as batch_op:
        batch_op.create_index(batch_op.f("ix_plan_item_session_id"), ["session_id"], unique=False)

    op.create_table(
        "project",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("job_id", sa.Integer(), nullable=True),
        sa.Column("name", sa.String(length=200), nullable=False),
        sa.Column("summary", sa.Text(), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("repo_url", sa.String(length=500), nullable=True),
        sa.Column("live_url", sa.String(length=500), nullable=True),
        sa.Column("start_date", sa.Date(), nullable=True),
        sa.Column("end_date", sa.Date(), nullable=True),
        sa.Column("is_active", sa.Boolean(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(["job_id"], ["job.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    with op.batch_alter_table("project", schema=None) as batch_op:
        batch_op.create_index(batch_op.f("ix_project_job_id"), ["job_id"], unique=False)

    op.create_table(
        "project_skill",
        sa.Column("project_id", sa.Integer(), nullable=False),
        sa.Column("skill_id", sa.Integer(), nullable=False),
        sa.ForeignKeyConstraint(["project_id"], ["project.id"]),
        sa.ForeignKeyConstraint(["skill_id"], ["skill.id"]),
        sa.PrimaryKeyConstraint("project_id", "skill_id"),
    )


def downgrade() -> None:
    op.drop_table("project_skill")
    with op.batch_alter_table("project", schema=None) as batch_op:
        batch_op.drop_index(batch_op.f("ix_project_job_id"))

    op.drop_table("project")
    with op.batch_alter_table("plan_item", schema=None) as batch_op:
        batch_op.drop_index(batch_op.f("ix_plan_item_session_id"))

    op.drop_table("plan_item")
    op.drop_table("job_skill")
    with op.batch_alter_table("achievement", schema=None) as batch_op:
        batch_op.drop_index(batch_op.f("ix_achievement_job_id"))

    op.drop_table("achievement")
    op.drop_table("tailoring_session")
    op.drop_table("skill")
    op.drop_table("profile")
    op.drop_table("job")
    op.drop_table("education")
    op.drop_table("certification")
