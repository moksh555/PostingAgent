import json
import uuid
from typing import Any

from app.errorsHandler.errors import (
    AppError,
    FailedToStartAgent,
    FailedToResumeAgent,
    )
from langgraph.types import Command  # type: ignore
from app.models.AgentModels import (
    AgentPostGenerationInterrupt,
    AgentRunRequest,
    AgentRunResponseCompleted,
    APIResponse
)
from app.models.healthCheckModel import HealthCheckModel
from langgraph.checkpoint.postgres import PostgresSaver # type: ignore
from app.services.agentGraph import workflow
from langgraph.checkpoint.serde.jsonplus import JsonPlusSerializer # type: ignore
from app.api.depends.repositoryDepends import get_postgres_repository_checkpointer


class AgentServices:
    SERDE = JsonPlusSerializer(
        allowed_msgpack_modules=[
            ("app.models.AgentModels", "AgentRunRequest"),
            ("app.models.AgentModels", "AgentSummary"),
            ("app.models.AgentModels", "LLMPostGeneration"),
            ("app.models.AgentModels", "AgentPost"),
        ],
    )
    
    def __init__(self) -> None:
        self.conn = get_postgres_repository_checkpointer().conn
        self.checkpointer = PostgresSaver(self.conn, serde=self.SERDE)
        get_postgres_repository_checkpointer().setup(self.checkpointer)
        self.graph = workflow.compile(checkpointer=self.checkpointer)

    def get_health_check(self) -> HealthCheckModel:
        return HealthCheckModel(
            status="ok",
            message="The Agent Service is running",
        )

    def startRun(
        self, 
        payload: AgentRunRequest
    ):

        try:
            threadId = str(uuid.uuid4())
            config = {"configurable": {"thread_id": threadId}}

            for chunk in self.graph.stream(
                {"payload": payload},
                config=config,
                stream_mode="updates",
                version="v2",
            ):
                if chunk["type"] == "updates":
                    for node_name, _state in chunk["data"].items():
                        yield APIResponse(
                            status="ok",
                            state="updates",
                            body={"node": node_name},
                        ).model_dump_json()

            finalView = self._buildClientView(self.graph, threadId, config)
            yield APIResponse(
                status="ok",
                state="result",
                body=finalView,
            ).model_dump_json()
        except AppError:
            raise
        except Exception as e:
            raise FailedToStartAgent(str(e)) from e

    def resumeRun(
        self,
        threadId: str,
        decision: AgentPostGenerationInterrupt,
    ):

        try:        
            config = {"configurable": {"thread_id": threadId}}

            for chunk in self.graph.stream(
                Command(resume=decision),
                config=config,
                stream_mode="updates",
                version="v2",
            ):
                if chunk["type"] == "updates":
                    for node_name, _state in chunk["data"].items():

                        yield APIResponse(
                            status="ok",
                            state="updates",
                            body={"node": node_name},
                        ).model_dump_json()

            finalView = self._buildClientView(self.graph, threadId, config)
            yield APIResponse(
                status="ok",
                state="result",
                body=finalView,
            ).model_dump_json()
        except AppError:
            raise
        except Exception as e:
            raise FailedToResumeAgent(str(e)) from e

    def _buildClientView(self, graph, threadId: str, config: dict) -> str:
        snapshot = graph.get_state(config)
        values = snapshot.values or {}
        posts = [p.model_dump(mode="json") for p in (values.get("posts") or [])]

        if snapshot.next:
            resumeResponse = AgentRunResponseCompleted(
                threadId=threadId,
                state="awaiting_review",
                draft=values.get("cacheDraft"),
                status="ok",
                userId=values.get("payload").userId,
                posts=posts,
                url=values.get("payload").url,
                numberOfPosts=values.get("payload").numberOfPosts,
                startDate=values.get("payload").startDate,
            )
            return resumeResponse

        completedResponse = AgentRunResponseCompleted(
            status="ok",
            state="completed",
            threadId=threadId,
            userId=values.get("payload").userId,
            posts=posts,
            url=values.get("payload").url,
            numberOfPosts=values.get("payload").numberOfPosts,
            startDate=values.get("payload").startDate,
        )
        return completedResponse
