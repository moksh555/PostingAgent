import uuid
from datetime import datetime, timezone
from langgraph.errors import GraphInterrupt  # type: ignore

from app.errorsHandler.errors import (
    AppError,
    FailedToStartAgent,
    FailedToResumeAgent,
    FailedToGetStateForUserThreads,
    FailedToGetThreads
    )
from langgraph.types import Command  # type: ignore
from app.models.AgentModels import (
    AgentPost,
    AgentRunRequest,
    AgentRunResponseCompleted,
    APIResponse,
    AgentResumeRunRequest,
    LLMPostGeneration,
)
from typing import List
from app.models.UserModels import (
    UserThreadState
)
from app.models.healthCheckModel import HealthCheckModel
from langgraph.checkpoint.postgres.aio import AsyncPostgresSaver  # type: ignore
from app.services.agentGraph import workflow
from langgraph.checkpoint.serde.jsonplus import JsonPlusSerializer # type: ignore
from app.api.depends.repositoryDepends import get_postgres_repository_checkpointer
from app.api.depends.repositoryDepends import get_postgres_repository_users_threads


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

    @staticmethod
    def _as_utc_aware(dt: datetime) -> datetime:
        """Comparable instant in UTC — naive payloads are treated as UTC (API contract)."""
        if dt.tzinfo is None:
            return dt.replace(tzinfo=timezone.utc)
        return dt.astimezone(timezone.utc)

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
        except GraphInterrupt:
            try:
                finalView = await self._buildClientView(self.graph, threadId, config)
            except ValueError as verr:
                raise FailedToStartAgent(str(verr)) from verr
            yield APIResponse(
                status="ok",
                state="result",
                body=finalView,
            ).model_dump_json() + "\n"
        except ValueError as verr:
            raise FailedToStartAgent(str(verr)) from verr
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
        except GraphInterrupt:
            try:
                finalView = await self._buildClientView(self.graph, payload.threadId, config)
            except ValueError as verr:
                raise FailedToResumeAgent(str(verr)) from verr
            yield APIResponse(
                status="ok",
                state="result",
                body=finalView,
            ).model_dump_json() + "\n"
        except ValueError as verr:
            raise FailedToResumeAgent(str(verr)) from verr
        except Exception as e:
            raise FailedToResumeAgent(str(e)) from e

    async def _buildClientView(self, graph, threadId: str, config: dict):
        snapshot = await graph.aget_state(config)
        values = snapshot.values or {}

        def _normalize_payload() -> AgentRunRequest:
            raw = values.get("payload")
            if raw is None:
                raise ValueError("Checkpoint missing payload")
            if isinstance(raw, AgentRunRequest):
                return raw
            if isinstance(raw, dict):
                return AgentRunRequest.model_validate(raw)
            raise ValueError(f"Unexpected payload shape: {type(raw).__name__}")

        def _serialize_posts(raw: list | None):
            rows = []
            for p in raw or []:
                if hasattr(p, "model_dump"):
                    rows.append(p.model_dump(mode="json"))
                elif isinstance(p, dict):
                    rows.append(
                        AgentPost.model_validate(p).model_dump(mode="json")
                    )
            return rows

        posts = _serialize_posts(values.get("posts"))

        payload = _normalize_payload()

        cache_raw = values.get("cacheDraft")
        cache_draft: LLMPostGeneration | None
        if cache_raw is None:
            cache_draft = None
        elif isinstance(cache_raw, LLMPostGeneration):
            cache_draft = cache_raw
        elif hasattr(cache_raw, "model_dump"):
            cache_draft = LLMPostGeneration.model_validate(
                cache_raw.model_dump(mode="json")
            )
        elif isinstance(cache_raw, dict):
            cache_draft = LLMPostGeneration.model_validate(cache_raw)
        else:
            cache_draft = None

        paused_for_review = bool(snapshot.next) or (cache_draft is not None)

        if paused_for_review:
            return AgentRunResponseCompleted(
                threadId=threadId,
                state="awaiting_review",
                draft=cache_draft,
                status="ok",
                userId=payload.userId,
                posts=posts,
                url=payload.url,
                numberOfPosts=payload.numberOfPosts,
                startDate=payload.startDate,
            )

        return AgentRunResponseCompleted(
            status="ok",
            state="completed",
            threadId=threadId,
            userId=payload.userId,
            posts=posts,
            url=payload.url,
            numberOfPosts=payload.numberOfPosts,
            startDate=payload.startDate,
        )
    
    async def getStateForUserThreads(self, userId: str) -> List[UserThreadState]:
        try:
            postgresDB = await get_postgres_repository_users_threads()
            threads : list[tuple[str]] =  await postgresDB.getThreads(userId)
            states: List[UserThreadState] = []
            now_utc = datetime.now(timezone.utc)
            for thread in threads:
                threadId = thread[0]
                config = {"configurable": {"thread_id": threadId}}
                snapshot = await self.graph.aget_state(config)
                values = snapshot.values or {}

                raw_payload = values.get("payload")
                if raw_payload is None:
                    continue
                try:
                    if isinstance(raw_payload, AgentRunRequest):
                        payload = raw_payload
                    elif isinstance(raw_payload, dict):
                        payload = AgentRunRequest.model_validate(raw_payload)
                    else:
                        continue
                except Exception:
                    continue

                start_cmp = self._as_utc_aware(payload.startDate)
                if snapshot.next:
                    status_str = "Paused"
                elif start_cmp >= now_utc:
                    status_str = "Assigned"
                else:
                    status_str = "Completed"

                state = {
                    "status": status_str,
                    "threadId": threadId,
                    "startDate": payload.startDate,
                    "numberOfPosts": payload.numberOfPosts,
                    "campaignURL": payload.url,
                }

                modelState = UserThreadState.model_validate(state)
                states.append(modelState)
            return states
        except FailedToGetThreads:
            raise
        except Exception as e:
            raise FailedToGetStateForUserThreads(f"Failed to get state for user threads: {e}") from e