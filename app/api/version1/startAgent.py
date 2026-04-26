
from fastapi import APIRouter, status, Depends, HTTPException  # type: ignore
from app.models.AgentModels import AgentRunRequest
from app.services.AgentServices import AgentServices
from fastapi.sse import EventSourceResponse # type: ignore
from app.api.depends.servicesDepends import get_agent_services
from app.errorsHandler.errors import AppError

router = APIRouter()


@router.post(
    "/startAgent",
    response_class=EventSourceResponse,
    status_code=status.HTTP_200_OK,
)
async def run_agent(
    payload: AgentRunRequest,
    agentServices: AgentServices = Depends(get_agent_services),
    ):
    """
    Run the agent with the given payload
    Args:
        payload: AgentRunRequest
    Returns:
        Streamed NDJSON (APIResponse); final `state=result` body matches AgentRunResponseCompleted when the run finishes or pauses.
    """
    try:
        async for chunk in agentServices.startRun(
            payload=payload,
        ):
            yield chunk
    except AppError as e:
        raise HTTPException(status_code=e.status_code, detail=e.message)
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
