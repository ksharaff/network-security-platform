"""CRUD endpoints for assets (known devices on the monitored network)."""

from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.models import Asset
from app.schemas.asset import AssetCreate, AssetRead, AssetUpdate

# prefix: every route below starts with /api/assets.
# tags: groups these endpoints under "assets" in the Swagger docs.
router = APIRouter(prefix="/api/assets", tags=["assets"])

# Shorthand for "an endpoint parameter that FastAPI fills by calling
# get_db". This is dependency injection: the endpoint declares what it
# needs, and the framework supplies it (and closes it afterwards).
DbSession = Annotated[Session, Depends(get_db)]


def _get_or_404(db: Session, asset_id: int) -> Asset:
    """Fetch one asset by primary key, or raise a 404 response."""
    asset = db.get(Asset, asset_id)
    if asset is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Asset {asset_id} not found",
        )
    return asset


def _duplicate_ip_error() -> HTTPException:
    """409 Conflict: the request is valid but clashes with existing data."""
    return HTTPException(
        status_code=status.HTTP_409_CONFLICT,
        detail="An asset with this IP address already exists",
    )


@router.post("", response_model=AssetRead, status_code=status.HTTP_201_CREATED)
def create_asset(payload: AssetCreate, db: DbSession) -> Asset:
    """Create an asset. Returns 201 and the stored record."""
    # model_dump() turns the validated schema into a plain dict, which
    # becomes the keyword arguments of the ORM model.
    asset = Asset(**payload.model_dump())
    db.add(asset)
    try:
        db.commit()
    except IntegrityError:
        # The database refused the row. The only uniqueness rule on this
        # table is ip_address, so that is the cause. We rely on the
        # UNIQUE constraint rather than checking first with a SELECT:
        # a check-then-insert has a race (two requests both pass the
        # check), whereas the constraint is always correct.
        # rollback() is mandatory: after a failed commit the session is
        # unusable until it is rolled back.
        db.rollback()
        raise _duplicate_ip_error() from None
    # Reload the row so server-generated values (id, timestamps) are present.
    db.refresh(asset)
    return asset


@router.get("", response_model=list[AssetRead])
def list_assets(
    db: DbSession,
    # Pagination: return a slice rather than the whole table.
    # limit = page size (1 to 500), offset = how many rows to skip.
    limit: int = Query(50, ge=1, le=500),
    offset: int = Query(0, ge=0),
) -> list[Asset]:
    """List assets, ordered by id."""
    # order_by is required for stable pages: without it, PostgreSQL may
    # return rows in any order, so page 2 could repeat rows from page 1.
    stmt = select(Asset).order_by(Asset.id).limit(limit).offset(offset)
    return list(db.scalars(stmt).all())


@router.get("/{asset_id}", response_model=AssetRead)
def get_asset(asset_id: int, db: DbSession) -> Asset:
    """Fetch a single asset."""
    return _get_or_404(db, asset_id)


@router.patch("/{asset_id}", response_model=AssetRead)
def update_asset(asset_id: int, payload: AssetUpdate, db: DbSession) -> Asset:
    """
    Partially update an asset (PATCH = change only the fields supplied;
    PUT would mean replace the whole record).
    """
    asset = _get_or_404(db, asset_id)

    # exclude_unset=True keeps only fields the client actually sent, so
    # omitted fields stay untouched. An explicit null on a nullable
    # field (e.g. "description": null) is kept, and clears the value.
    changes = payload.model_dump(exclude_unset=True)
    for field, value in changes.items():
        setattr(asset, field, value)

    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        raise _duplicate_ip_error() from None
    db.refresh(asset)
    return asset


@router.delete("/{asset_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_asset(asset_id: int, db: DbSession) -> None:
    """Delete an asset. 204 means success with an empty response body."""
    asset = _get_or_404(db, asset_id)
    db.delete(asset)
    db.commit()