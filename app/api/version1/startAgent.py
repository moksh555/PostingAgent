
from fastapi import APIRouter, status, Depends, HTTPException  # type: ignore

from app.models.AgentModels import AgentRunRequest, AgentRunResponseCompleted
from app.services.AgentServices import AgentServices
from fastapi.responses import StreamingResponse  # type: ignore
from app.api.depends.servicesDepends import get_agent_services
from app.errorsHandler.errors import AppError

router = APIRouter()
agent_services = AgentServices()


@router.post(
    "/startAgent",
    response_model=AgentRunResponseCompleted,
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
        return StreamingResponse(
            agentServices.startRun(
                payload=payload,
            ),
            media_type="application/x-ndjson",
        )
    except AppError as e:
        raise HTTPException(status_code=e.status_code, detail=e.message)
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
