from fastapi import APIRouter, status, Depends  # type: ignore
from app.models.AgentModels import (
    AgentResumeRunRequest,
    )
from fastapi.sse import EventSourceResponse # type: ignore
from app.services.AgentServices import AgentServices
from app.api.depends.servicesDepends import get_agent_services

router = APIRouter()


@router.post(
    "/resumeAgent", 
    response_class=EventSourceResponse, 
    status_code=status.HTTP_200_OK
    )
async def resume_agent(
    payload: AgentResumeRunRequest, 

    agentServices : AgentServices = Depends(get_agent_services)
    ):
    """
    Resume the agent with the given payload
    Args:
        payload: AgentResumeRunRequest (threadId + decision)
    Returns:
        Streamed NDJSON (APIResponse); final `state=result` body matches AgentRunResponseCompleted when the run finishes or pauses.
    """

    async for chunk in agentServices.resumeRun(
        payload=payload
        ):
        yield chunk