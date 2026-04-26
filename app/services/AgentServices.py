import uuid

from app.errorsHandler.errors import (
    AppError,
    FailedToStartAgent,
    FailedToResumeAgent,
    )
from langgraph.types import Command  # type: ignore
from app.models.AgentModels import (
    AgentRunRequest,
    AgentRunResponseCompleted,
    APIResponse,
    AgentResumeRunRequest,
)
from app.models.healthCheckModel import HealthCheckModel
from langgraph.checkpoint.postgres.aio import AsyncPostgresSaver  # type: ignore
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
            ('app.models.AgentModels', 'AgentPostGenerationInterrupt'),
        ],
    )
    
    def __init__(self) -> None:
        self.graph = None
        self.checkpointer = None
    
    @classmethod
    async def create(cls) -> "AgentServices":
        instance = cls()
        repo = await get_postgres_repository_checkpointer()
        instance.conn = repo.conn
        instance.checkpointer = AsyncPostgresSaver(instance.conn, serde=cls.SERDE)
        await repo.setup(instance.checkpointer)
        instance.graph = workflow.compile(checkpointer=instance.checkpointer)
        return instance

    def get_health_check(self) -> HealthCheckModel:
        return HealthCheckModel(
            status="ok",
            message="The Agent Service is running",
        )

    async def startRun(
        self, 
        payload: AgentRunRequest
    ):

        try:
            threadId = str(uuid.uuid4())
            config = {"configurable": {"thread_id": threadId}}

            async for chunk in self.graph.astream(
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
                        ).model_dump_json() + "\n"

            finalView = await self._buildClientView(self.graph, threadId, config)
            yield APIResponse(
                status="ok",
                state="result",
                body=finalView,
            ).model_dump_json() + "\n"
        except AppError:
            raise
        except Exception as e:
            raise FailedToStartAgent(str(e))

    async def resumeRun(
        self,
        payload: AgentResumeRunRequest,
    ):

        try:        
            config = {"configurable": {"thread_id": payload.threadId}}

            async for chunk in self.graph.astream(
                Command(resume=payload.decision),
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
                        ).model_dump_json() + "\n"

            finalView = await self._buildClientView(self.graph, payload.threadId, config)
            yield APIResponse(
                status="ok",
                state="result",
                body=finalView,
            ).model_dump_json() + "\n"
        except AppError:
            raise
        except Exception as e:
            raise FailedToResumeAgent(str(e)) from e

    async def _buildClientView(self, graph, threadId: str, config: dict):
        snapshot = await graph.aget_state(config)
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
