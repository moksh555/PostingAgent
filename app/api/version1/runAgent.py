import logging

from fastapi import APIRouter, HTTPException, status  # type: ignore
from pydantic import ValidationError  # type: ignore

from app.models.AgentModels import AgentRunRequest, AgentRunResponse
from app.services.AgentServices import AgentServices

router = APIRouter()
agent_services = AgentServices()


@router.post(
    "/runAgent",
    response_model=AgentRunResponse,
    status_code=status.HTTP_200_OK,
)
async def run_agent(payload: AgentRunRequest):
    """
    Run the agent with the given payload
    Args:
        payload: AgentRunRequest
    Returns:
        AgentRunResponse
    """
    try:
        return agent_services.runAgent(
            payload=payload,
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
