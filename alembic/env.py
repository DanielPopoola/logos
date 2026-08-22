from logging.config import fileConfig

from alembic import context
from app.config import settings
from app.database import Base
from app.models import (
    processing_job,  # noqa: E501, F401
    sermon,  # noqa: F401
    sermon_analysis,  # noqa: F401,
    sermon_chunk,  # noqa: F401,
    session,  # noqa: F401
    taxonomy,  # noqa: F401,
    user,  # noqa: F401
    user_note,  # noqa: F401
    user_sermon,  # noqa: F401,
)

config = context.config
config.set_main_option("sqlalchemy.url", settings.database_url)

if config.config_file_name is not None:
    fileConfig(config.config_file_name)

target_metadata = Base.metadata


def run_migrations_offline() -> None:
    url = config.get_main_option("sqlalchemy.url")
    context.configure(
        url=url,
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
    )
    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    from sqlalchemy import engine_from_config, pool

    connectable = engine_from_config(
        config.get_section(config.config_ini_section, {}),
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,
    )

    with connectable.connect() as connection:
        context.configure(connection=connection, target_metadata=target_metadata)
        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
