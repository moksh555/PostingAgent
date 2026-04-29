import json

from fastapi import APIRouter, status, Depends  # type: ignore
from starlette.responses import StreamingResponse  # type: ignore

from app.models.AgentModels import AgentRunRequest
from app.services.AgentServices import AgentServices
from app.api.depends.servicesDepends import get_agent_services
from app.errorsHandler.errors import AppError

router = APIRouter()


@router.post("/startAgent", status_code=status.HTTP_200_OK)
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

    async def ndjson():
        try:
            async for chunk in agentServices.startRun(payload=payload):
                yield chunk
        except AppError as e:
            yield json.dumps(
                {
                    "status": "error",
                    "state": "error",
                    "body": {"message": e.message, "code": e.code},
                }
            ) + "\n"
        except Exception as e:
            yield json.dumps(
                {
                    "status": "error",
                    "state": "error",
                    "body": {"message": str(e), "code": "internal_error"},
                }
            ) + "\n"

    return StreamingResponse(ndjson(), media_type="application/x-ndjson")
