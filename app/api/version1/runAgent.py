import logging

from fastapi import APIRouter, HTTPException, status  # type: ignore
from pydantic import ValidationError  # type: ignore

from app.models.AgentModels import AgentRunRequest, AgentRunResponseCompleted
from app.services.AgentServices import AgentServices
from fastapi.responses import StreamingResponse  # type: ignore
from app.api.depends.servicesDepends import get_agent_services
router = APIRouter()
agent_services = AgentServices()


@router.post(
    "/startAgent",
    response_model=AgentRunResponseCompleted,
    status_code=status.HTTP_200_OK,
)
async def run_agent(payload: AgentRunRequest):
    """
    Run the agent with the given payload
    Args:
        payload: AgentRunRequest
    Returns:
        Streamed NDJSON (APIResponse); final `state=result` body matches AgentRunResponseCompleted when the run finishes or pauses.
    """
    try:
        return StreamingResponse(
            agent_services.startRun(
                payload=payload,
            )
        )
    except ValidationError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e),
        ) from e
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=str(e),
        ) from e
