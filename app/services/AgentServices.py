from datetime import datetime

from app.models.AgentModels import AgentRunResponse
from app.models.healthCheckModel import HealthCheckModel


class AgentServices:
    def __init__(self) -> None:
        pass

    def get_health_check(self) -> HealthCheckModel:
        return HealthCheckModel(
            status="ok",
            message="The Agent Service is running",
        )

    def runAgent(self, numberOfPosts: int, startDate: datetime) -> AgentRunResponse:

        return AgentRunResponse(
            status="ok",
            message=f"Scheduled {numberOfPosts} posts starting {startDate.isoformat()}",
            numberOfPosts=numberOfPosts,
            startDate=startDate,
        )
