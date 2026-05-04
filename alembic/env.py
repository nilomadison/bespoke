import sys
from pathlib import Path
from logging.config import fileConfig

from sqlalchemy import pool
from alembic import context

# Make src/ importable when Alembic runs from the project root
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from src.models import Base  # noqa: E402 — imports all models so autogenerate sees them
from src.db.engine import engine as sync_engine  # noqa: E402

config = context.config
if config.config_file_name is not None:
    fileConfig(config.config_file_name)

# target_metadata must include all model tables; any model missing from
# src/models/__init__.py will silently be absent from autogenerate output.
target_metadata = Base.metadata


def run_migrations_offline() -> None:
    url = str(sync_engine.url)
    context.configure(
        url=url,
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
    )
    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    with sync_engine.connect() as connection:
        context.configure(
            connection=connection,
            target_metadata=target_metadata,
            render_as_batch=True,  # required for SQLite ALTER TABLE support
        )
        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
