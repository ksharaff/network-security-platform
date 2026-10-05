"""
Alembic environment script.

Alembic runs this file every time you use an `alembic` command that
touches the database. Its job is to answer two questions:
  1. Which database do I connect to?
  2. What should the schema look like? (the "target metadata")
"""

from logging.config import fileConfig

from alembic import context

# Our settings object reads DATABASE_URL from .env, so the password
# never appears in the committed alembic.ini.
from app.core.config import settings  # noqa: F401

# Base.metadata is SQLAlchemy's catalogue of every table defined by a
# model. `engine` is the app's existing connection pool, reused so
# migrations and the application always talk to the same database.
from app.core.database import Base, engine

# Imported only for its side effect: loading every model class so it
# registers on Base.metadata. "noqa: F401" tells the linter (ruff) that
# an import it considers unused is intentional.
import app.models  # noqa: F401

# Alembic's config object, which gives access to alembic.ini values.
config = context.config

# Set up Python logging using the [loggers] sections in alembic.ini.
# disable_existing_loggers=False stops this from silencing the
# application's own loggers if they are ever active in the same process.
if config.config_file_name is not None:
    fileConfig(config.config_file_name, disable_existing_loggers=False)

# What autogenerate compares the real database against.
target_metadata = Base.metadata


def run_migrations_offline() -> None:
    """
    Offline mode: emit the migration as SQL text without connecting.

    Useful for generating a script to hand to a DBA. We give Alembic
    only a URL, with no live connection.
    """
    context.configure(
        url=settings.database_url,
        target_metadata=target_metadata,
        # Write real values into the SQL text instead of placeholders.
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
        # Also detect changed column types (e.g. String(50) to String(100)).
        # Alembic ignores type changes by default.
        compare_type=True,
    )

    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    """
    Online mode (the normal one): connect to the database and apply
    migrations directly.
    """
    # Borrow a connection from the application's engine. The `with`
    # block returns it to the pool when finished.
    with engine.connect() as connection:
        context.configure(
            connection=connection,
            target_metadata=target_metadata,
            compare_type=True,
        )

        # Run all migrations inside one transaction: if one fails,
        # the database rolls back to how it was before.
        with context.begin_transaction():
            context.run_migrations()


# Alembic sets an "offline mode" flag when run with `--sql`.
if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()