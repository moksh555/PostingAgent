from fastapi import APIRouter  # type: ignore

from app.api.version1.healthCheck import router as health_check_router
from app.api.version1.startAgent import router as run_agent_router
from app.api.version1.resumeAgent import router as resume_agent_router
from app.api.version1.getUserThreadStates import router as get_user_thread_states_router
from app.api.version1.agentThreadSnapshot import router as agent_thread_snapshot_router


router = APIRouter()

router.include_router(health_check_router, prefix="/agentservices/v1", tags=["health_check"])
router.include_router(run_agent_router, prefix="/agentservices/v1", tags=["agent"])
router.include_router(resume_agent_router, prefix="/agentServices/v1", tags=["agent"])
router.include_router(get_user_thread_states_router, prefix="/agentServices/v1", tags=["agent"])
router.include_router(agent_thread_snapshot_router, prefix="/agentServices/v1", tags=["agent"])