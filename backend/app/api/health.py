"""Health check endpoint."""

from fastapi import APIRouter

router = APIRouter(prefix="/api", tags=["system"])


@router.get("/health")
def health() -> dict:
    """Report the service is up."""
    return {"status": "ok"}
