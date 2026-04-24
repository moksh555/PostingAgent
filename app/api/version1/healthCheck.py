from fastapi import APIRouter  # type:ignore
from app.models.healthCheckModel import HealthCheckModel

router = APIRouter()


@router.get("/healthChecks/live")
async def health_check() -> HealthCheckModel:
    return HealthCheckModel(
        status="ok", message="The whole Marketing Agent System is running"
    )
