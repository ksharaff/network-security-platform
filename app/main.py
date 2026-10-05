"""Application entry point — creates the FastAPI app and mounts routers."""

from fastapi import FastAPI

from app.api import health
from app.api import assets

from app.core.config import settings

app = FastAPI(
    title=settings.app_name,
    description=(
        "Security monitoring platform: ingests network telemetry, applies "
        "detection rules, scores device risk, and manages incidents."
    ),
    version="0.1.0",
)

# Mount the health router. 'tags' groups endpoints in the generated docs.
app.include_router(health.router, tags=["system"])
app.include_router(assets.router)

