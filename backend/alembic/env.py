import os
from logging.config import fileConfig

from sqlalchemy import engine_from_config, pool

from alembic import context
from src.core.config import settings
from src.db import models as db_models  # noqa: F401
from src.db.base import Base

config = context.config

if config.config_file_name is not None:
    fileConfig(config.config_file_name)

# Use DATABASE_URL from env (docker-compose) or fall back to settings
db_url = os.getenv("DATABASE_URL") or getattr(settings, "DATABASE_URL", None)
if db_url:
    config.set_main_option("sqlalchemy.url", db_url)

target_metadata = Base.metadata
managed_tables = set(target_metadata.tables.keys())


def include_object(object_, name, type_, reflected, compare_to):
    """Limit autogenerate/check to backend-managed tables only."""
    if type_ == "table":
        if reflected and name not in managed_tables:
            return False
        if not reflected and name not in managed_tables:
            return False

    table_name = None
    table = getattr(object_, "table", None)
    if table is not None:
        table_name = table.name
    elif type_ == "table":
        table_name = name

    if table_name and table_name not in managed_tables:
        return False

    return True


def run_migrations_offline() -> None:
    url = config.get_main_option("sqlalchemy.url")
    context.configure(
        url=url,
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
        compare_type=True,
        include_object=include_object,
    )

    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    connectable = engine_from_config(
        config.get_section(config.config_ini_section, {}),
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,
    )

    with connectable.connect() as connection:
        context.configure(
            connection=connection,
            target_metadata=target_metadata,
            compare_type=True,
            include_object=include_object,
        )

        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
