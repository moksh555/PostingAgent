from fastapi import APIRouter #type: ignore
from app.api.version1.healthCheck import router as health_check_router
from app.api.version1.login import router as login_router
from app.api.version1.refresh import router as refresh_router
from app.api.version1.register import router as register_router

router = APIRouter()

router.include_router(health_check_router, prefix="/userservices/v1", tags=["health_check"])
router.include_router(login_router, prefix="/userservices/v1", tags=["auth"])
router.include_router(register_router, prefix="/userservices/v1", tags=["auth"])
router.include_router(refresh_router, prefix="/userservices/v1", tags=["auth"])
