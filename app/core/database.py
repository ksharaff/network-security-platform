"""Database engine, session factory, and the declarative base class."""

from collections.abc import Generator

from sqlalchemy import create_engine
from sqlalchemy.orm import DeclarativeBase, Session, sessionmaker

from app.core.config import settings

# The engine owns the connection pool. Create exactly one per application.
engine = create_engine(
    settings.database_url,
    # Ping a pooled connection before handing it out. Without this you get
    # "server closed the connection unexpectedly" after a DB restart.
    pool_pre_ping=True,
    echo=settings.sql_echo,
)

# A factory producing Session objects — your unit of work.
SessionLocal = sessionmaker(
    bind=engine,
    # Don't auto-flush pending changes before every query.
    autoflush=False,
    # Require an explicit commit() so nothing is written by accident.
    autocommit=False,
)


class Base(DeclarativeBase):
    """
    Parent class for every ORM model. SQLAlchemy collects table
    definitions from subclasses of this, which is how Alembic later
    discovers what the schema should look like.
    """


def get_db() -> Generator[Session, None, None]:
    """
    FastAPI dependency supplying a database session per request.

    FastAPI calls this, hands the yielded session to the endpoint, then
    resumes after the yield once the response is sent — so the session is
    always closed, including when the endpoint raises.
    """
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()