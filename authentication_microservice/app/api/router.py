from fastapi import APIRouter #type: ignore
from app.api.version1.healthCheck import router as health_check_router

router = APIRouter()

router.include_router(health_check_router, prefix="/userservices/v1", tags=["health_check"])
