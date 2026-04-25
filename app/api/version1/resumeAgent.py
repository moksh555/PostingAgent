from fastapi import APIRouter, HTTPException, status, Depends # type: ignore
from app.models.AgentModels import (
    AgentPostGenerationInterrupt, 
    AgentRunResponseCompleted,
    AgentResumeRunRequest,
    )
from app.services.AgentServices import AgentServices
from app.api.depends.servicesDepends import get_agent_services
from fastapi.responses import StreamingResponse # type: ignore
router = APIRouter()


@router.post(
    "/resumeAgent", 
    response_model=AgentRunResponseCompleted, 
    status_code=status.HTTP_200_OK
    )
def resume_agent(
    payload: AgentResumeRunRequest, 

    agentServices : AgentServices = Depends(get_agent_services)
    ):
    """
    Resume the agent with the given payload
    Args:
        payload: AgentPostGenerationInterrupt
    Returns:
        Streamed NDJSON (APIResponse); final `state=result` body matches AgentRunResponseCompleted when the run finishes or pauses.
    """

    return StreamingResponse(
        agentServices.resumeRun(
            payload=payload,
        ),
        media_type="application/x-ndjson",
    )