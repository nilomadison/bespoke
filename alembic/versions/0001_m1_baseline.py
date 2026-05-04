"""m1_baseline

Marks the state of all M1 tables (profile, job, achievement, skill, job_skill,
project, project_skill, education, certification). These tables were created
by Base.metadata.create_all() during development, so this migration is a
no-op — it only establishes the migration baseline that subsequent migrations
can build on.

Revision ID: 0001_m1_baseline
Revises:
Create Date: 2026-05-01

"""
from typing import Sequence, Union

revision: str = "0001_m1_baseline"
down_revision: Union[str, Sequence[str], None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    pass  # M1 tables already exist via create_all()


def downgrade() -> None:
    pass
