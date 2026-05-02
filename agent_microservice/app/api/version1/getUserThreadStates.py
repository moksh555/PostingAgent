from fastapi import APIRouter, Depends, HTTPException, status #type: ignore
from app.services.AgentServices import AgentServices
from app.models.UserModels import UserThreadState
from app.api.depends.servicesDepends import get_agent_services
from app.errorsHandler.errors import (
    FailedToGetStateForUserThreads, 
    FailedToGetThreads
)

router = APIRouter()

@router.get("/getUserThreadStates/{userId}")
async def get_user_thread_states(
    userId: str, 
    agentServices: AgentServices = Depends(get_agent_services)
    ) -> list[UserThreadState]:
    """
    Get the thread states for a user
    Args:
        userId: str (the user ID)
    Returns:
        list[UserThreadState] (the thread states for the user)
    """
    try:
        return await agentServices.getStateForUserThreads(userId)
    except FailedToGetStateForUserThreads:
        raise 
    except FailedToGetThreads:
        raise 
    except Exception as e:
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=f"An unexpected error occurred: {e}")