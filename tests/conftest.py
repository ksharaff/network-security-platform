"""
Shared test fixtures.

The key design: one real TimescaleDB container is started per test run,
the real Alembic migrations are applied to it, and every test talks to it
through the real FastAPI app. Only the database connection is swapped.
"""

import os
import time
from collections.abc import Generator
from pathlib import Path

# SAFETY + CI: app.core.config requires DATABASE_URL at import time and
# would otherwise read it from your .env (the DEV database). We set a
# dummy value BEFORE any app import, so tests can never touch the dev
# database, and so this works in CI where no .env exists. The dummy is
# never connected to: tests replace the app's database dependency below.
os.environ["DATABASE_URL"] = "postgresql+psycopg://unused:unused@localhost:5432/unused"

import pytest  # noqa: E402  (must come after the environment line above)
from alembic import command  # noqa: E402
from alembic.config import Config  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402
from sqlalchemy import Engine, create_engine, text  # noqa: E402
from sqlalchemy.exc import OperationalError  # noqa: E402
from sqlalchemy.orm import Session, sessionmaker  # noqa: E402
from testcontainers.postgres import PostgresContainer  # noqa: E402

from app.core.database import get_db  # noqa: E402
from app.main import app  # noqa: E402

# Use the SAME image as docker-compose.yml so it is already downloaded
# and tests run against what production uses. Check yours with:
#   grep image docker-compose.yml
# and change this line if the tag differs.
TIMESCALE_IMAGE = "timescale/timescaledb:latest-pg16"

REPO_ROOT = Path(__file__).resolve().parent.parent


def _wait_until_ready(engine: Engine, timeout: float = 60.0) -> None:
    """
    Poll the database until it accepts connections.

    The Postgres image starts a temporary server to run its init scripts,
    shuts it down, then starts the real one. "Container started" does
    therefore not mean "database ready"; polling is the reliable check.
    """
    deadline = time.monotonic() + timeout
    while True:
        try:
            with engine.connect() as connection:
                connection.execute(text("SELECT 1"))
            return
        except OperationalError:
            if time.monotonic() > deadline:
                raise
            time.sleep(0.5)


def _run_migrations(engine: Engine) -> None:
    """Apply every Alembic migration to the test database."""
    config = Config(str(REPO_ROOT / "alembic.ini"))
    # Absolute path, so this works no matter where pytest is launched from.
    config.set_main_option("script_location", str(REPO_ROOT / "migrations"))

    with engine.begin() as connection:
        # Hand our connection to migrations/env.py (see do_run_migrations).
        config.attributes["connection"] = connection
        command.upgrade(config, "head")


@pytest.fixture(scope="session")
def engine() -> Generator[Engine, None, None]:
    """
    A connection pool to a throwaway database.

    scope="session": created once for the whole test run, because
    starting a container takes seconds. The `with` block destroys the
    container afterwards, even if tests fail.
    """
    with PostgresContainer(TIMESCALE_IMAGE, driver="psycopg") as postgres:
        test_engine = create_engine(postgres.get_connection_url(), pool_pre_ping=True)
        _wait_until_ready(test_engine)
        # Using the real migrations means the tests also prove the
        # migrations produce a working schema.
        _run_migrations(test_engine)
        yield test_engine
        test_engine.dispose()


@pytest.fixture(scope="session")
def session_factory(engine: Engine) -> sessionmaker[Session]:
    """A factory producing database sessions bound to the test database."""
    return sessionmaker(bind=engine, autoflush=False)


@pytest.fixture(autouse=True)
def clean_tables(engine: Engine) -> Generator[None, None, None]:
    """
    Empty the tables after EVERY test (autouse=True applies it to all
    tests without being requested), so tests cannot affect each other.

    TRUNCATE removes all rows quickly; RESTART IDENTITY resets the id
    counter so each test starts again from id 1.
    """
    yield
    with engine.begin() as connection:
        connection.execute(text("TRUNCATE assets RESTART IDENTITY CASCADE"))


@pytest.fixture
def client(session_factory: sessionmaker[Session]) -> Generator[TestClient, None, None]:
    """
    A test client that calls the real app, backed by the test database.

    dependency_overrides tells FastAPI: wherever an endpoint asks for
    get_db, call this function instead. That single swap is how the
    whole app ends up using the container.
    """

    def override_get_db() -> Generator[Session, None, None]:
        db = session_factory()
        try:
            yield db
        finally:
            db.close()

    app.dependency_overrides[get_db] = override_get_db
    with TestClient(app) as test_client:
        yield test_client
    app.dependency_overrides.clear()