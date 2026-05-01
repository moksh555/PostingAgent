from fastapi import APIRouter, Depends  # type: ignore

from app.api.depends.servicesDepends import get_agent_services
from app.errorsHandler.errors import FailedToGetThreadSnapshot
from app.models.AgentModels import AgentRunResponseCompleted
from app.services.AgentServices import AgentServices

router = APIRouter()


@router.get("/agentThreadSnapshot/{thread_id}")
async def get_agent_thread_snapshot(
    thread_id: str,
    agent_services: AgentServices = Depends(get_agent_services),
) -> AgentRunResponseCompleted:
    """Return the latest client view for a checkpointed thread (paused or completed).

    Mirrors the JSON body streamed as `APIResponse(..., state=result, ...)`
    without running the graph."""
    try:
        return await agent_services.get_thread_snapshot(thread_id)
    except FailedToGetThreadSnapshot:
        raise
