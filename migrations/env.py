"""Alembic environment: the analysis DB URL comes from .env, never from alembic.ini."""

from logging.config import fileConfig

from alembic import context
from sqlalchemy import create_engine

from jobpipe.config import Settings
from jobpipe.db.schema import metadata

config = context.config
if config.config_file_name is not None:
    fileConfig(config.config_file_name)

target_metadata = metadata


def get_url() -> str:
    # Tests can pass an explicit URL; otherwise use the analysis DB from .env
    url = config.get_main_option("sqlalchemy.url")
    if url:
        return url
    s = Settings()
    return s.url(s.analysis_db)


def run_migrations_offline() -> None:
    context.configure(url=get_url(), target_metadata=target_metadata, literal_binds=True)
    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    connectable = create_engine(get_url())
    with connectable.connect() as connection:
        context.configure(connection=connection, target_metadata=target_metadata)
        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
