import logging
import uuid
from typing import Any
import json 
from langgraph.types import Command  # type: ignore

from app.models.AgentModels import (
    AgentPostGenerationInterrupt,
    AgentRunRequest,
)
from app.models.healthCheckModel import HealthCheckModel
from app.repository.postgreSQL import PostgreSQLRepository

logger = logging.getLogger(__name__)


class AgentServices:
    def __init__(self) -> None:
        pass

    def get_health_check(self) -> HealthCheckModel:
        return HealthCheckModel(
            status="ok",
            message="The Agent Service is running",
        )

    def startRun(self, payload: AgentRunRequest) -> dict[str, Any]:
        threadId = str(uuid.uuid4())
        config = {
            "configurable": {"thread_id": threadId}}

        graph = PostgreSQLRepository().get_graph()

        for chunk in graph.stream(
            {"payload": payload},
            config=config,
            stream_mode="updates",
            version="v2",
        ):
            if chunk["type"] == "updates":
                for node_name, _state in chunk["data"].items():
                    yield json.dumps({"state": "updates", "node": node_name})

        return self._buildClientView(graph, threadId, config)

    def resumeRun(
        self,
        threadId: str,
        decision: AgentPostGenerationInterrupt,
    ) -> dict[str, Any]:
        config = {"configurable": {"thread_id": threadId}}

        graph = PostgreSQLRepository().get_graph()

        for chunk in graph.stream(
            Command(resume=decision),
            config=config,
            stream_mode="updates",
            version="v2",
        ):
            if chunk["type"] == "updates":
                for node_name, _state in chunk["data"].items():
                    yield json.dumps({"state": "updates", "node": node_name})

        return self._buildClientView(graph, threadId, config)

    def _buildClientView(self, graph, threadId: str, config: dict) -> str:
        snapshot = graph.get_state(config)
        values = snapshot.values or {}
        posts = [p.model_dump(mode="json") for p in (values.get("posts") or [])]

        if snapshot.next:
            cacheDraft = values.get("cacheDraft")
            draft = None
            if cacheDraft:
                draft = {
                    "content": cacheDraft.content,
                    "publishDate": cacheDraft.publishDate.isoformat(),
                }
            return json.dumps({
                "threadId": threadId,
                "state": "awaiting_review",
                "draft": draft,
                "posts": posts,
            })

        return json.dumps({
            "threadId": threadId,
            "state": "completed",
            "draft": None,
            "posts": posts,
        })
