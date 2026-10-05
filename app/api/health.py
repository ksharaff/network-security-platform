"""Health check endpoint — reports whether the app can reach its database."""

from fastapi import APIRouter, Depends, Response, status
from sqlalchemy import text
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.database import get_db

# A router groups related endpoints; main.py mounts it onto the app.
router = APIRouter()


@router.get("/health")
def health_check(response: Response, db: Session = Depends(get_db)) -> dict:
    """
    Returns 200 when the database is reachable, 503 when it is not.

    A health check that only proves the web server is running is close to
    useless — it reports healthy while every request fails. This one
    executes a trivial query to prove the whole path works.

    Note 'def', not 'async def': this performs blocking database I/O, so
    FastAPI runs it in a thread pool rather than on the event loop.
    """
    try:
        # text() marks this as literal SQL. SELECT 1 is the cheapest
        # statement that still proves a round trip happened.
        db.execute(text("SELECT 1"))
        database_ok = True
    except SQLAlchemyError:
        database_ok = False

    if not database_ok:
        response.status_code = status.HTTP_503_SERVICE_UNAVAILABLE

    return {
        "status": "ok" if database_ok else "degraded",
        "application": settings.app_name,
        "database": "connected" if database_ok else "unreachable",
    }