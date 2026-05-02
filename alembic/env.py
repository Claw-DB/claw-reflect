"""Alembic environment configuration with async SQLAlchemy engine support."""

from __future__ import annotations

import asyncio
from logging.config import fileConfig

from sqlalchemy.ext.asyncio import create_async_engine

import claw_reflect.models.api_key  # noqa: F401
import claw_reflect.models.contradiction  # noqa: F401
import claw_reflect.models.decay  # noqa: F401
import claw_reflect.models.memory  # noqa: F401
import claw_reflect.models.preference  # noqa: F401
import claw_reflect.models.profile  # noqa: F401
import claw_reflect.models.reflection  # noqa: F401
from alembic import context

# ---------------------------------------------------------------------------
# Import all models so that Base.metadata is fully populated before
# autogenerate / migration runs inspect it.
# ---------------------------------------------------------------------------
from claw_reflect.config import settings
from claw_reflect.db.base import Base

# ---------------------------------------------------------------------------
# Alembic Config object — gives access to values in alembic.ini
# ---------------------------------------------------------------------------
config = context.config

# Interpret the config file for Python logging if present
if config.config_file_name is not None:
    fileConfig(config.config_file_name)

# Override the sqlalchemy.url from our application settings
config.set_main_option("sqlalchemy.url", settings.database_url)

target_metadata = Base.metadata


# ---------------------------------------------------------------------------
# Migration helpers
# ---------------------------------------------------------------------------


def run_migrations_offline() -> None:
    """Run migrations in *offline* mode (no live DB connection required)."""
    url = config.get_main_option("sqlalchemy.url")
    context.configure(
        url=url,
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
    )

    with context.begin_transaction():
        context.run_migrations()


async def run_migrations_online_async() -> None:
    """Run migrations in *online* mode using an AsyncEngine."""
    connectable = create_async_engine(settings.database_url, echo=False)

    async with connectable.connect() as connection:
        await connection.run_sync(
            lambda conn: context.configure(
                connection=conn,
                target_metadata=target_metadata,
                compare_type=True,
            )
        )
        await connection.run_sync(lambda _: context.run_migrations())

    await connectable.dispose()


def run_migrations_online() -> None:
    """Entry point for online migrations — delegates to the async runner."""
    asyncio.run(run_migrations_online_async())


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
