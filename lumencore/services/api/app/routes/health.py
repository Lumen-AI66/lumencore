from fastapi import APIRouter

from ..config import settings

router = APIRouter()


@router.get("/health")
def health() -> dict:
    return {
        "status": "ok",
        "service": "lumencore-api",
        "phase": settings.system_phase,
        "release_id": settings.release_id,
    }
