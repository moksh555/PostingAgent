from fastapi import APIRouter  # type: ignore

from app.api.version1.healthCheck import router as health_check_router
from app.api.version1.runAgent import router as run_agent_router

router = APIRouter()

router.include_router(health_check_router, prefix="/api/v1", tags=["health_check"])
router.include_router(run_agent_router, prefix="/api/v1", tags=["agent"])
