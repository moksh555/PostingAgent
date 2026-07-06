import asyncio
from datetime import datetime, timezone
from types import SimpleNamespace

import pytest

from app.errorsHandler.errors import FailedToGetThreadSnapshot
from app.models.AgentModels import AgentPost, AgentRunRequest, LLMPostGeneration
import app.services.AgentServices as services_module
from app.services.AgentServices import AgentServices


def run(coro):
    return asyncio.run(coro)


def make_payload(*, start_date=None):
    return AgentRunRequest(
        userId="user-123",
        url="https://example.com/campaign",
        numberOfPosts=2,
        startDate=start_date or datetime(2026, 5, 1, 9, 0),
    )


def make_post(content="Accepted post"):
    return AgentPost(
        content=content,
        publishDate=datetime(2026, 5, 2, 9, 0),
        platform="LinkedIn",
        postNumber=1,
    )


class FakeGraph:
    def __init__(self, snapshots):
        self.snapshots = snapshots
        self.configs = []

    async def aget_state(self, config):
        self.configs.append(config)
        thread_id = config["configurable"]["thread_id"]
        snapshot = self.snapshots[thread_id]
        if isinstance(snapshot, BaseException):
            raise snapshot
        return snapshot


class FakeThreadsRepository:
    def __init__(self, threads):
        self.threads = threads

    async def getThreads(self, user_id):
        assert user_id == "user-123"
        return [(thread_id,) for thread_id in self.threads]


def snapshot(values, *, next_nodes=()):
    return SimpleNamespace(values=values, next=next_nodes)


class TestBuildClientView:
    def test_cacheDraftMarksSnapshotAwaitingReviewAndNormalizesDicts(self):
        service = AgentServices()
        payload = make_payload()
        draft = LLMPostGeneration(
            content="Draft awaiting human review",
            publishDate=datetime(2026, 5, 3, 9, 0),
        )
        service.graph = FakeGraph(
            {
                "thread-paused": snapshot(
                    {
                        "payload": payload.model_dump(mode="json"),
                        "cacheDraft": draft.model_dump(mode="json"),
                        "posts": [make_post().model_dump(mode="json")],
                    }
                )
            }
        )

        result = run(service.get_thread_snapshot("thread-paused"))

        assert result.state == "awaiting_review"
        assert result.threadId == "thread-paused"
        assert result.userId == "user-123"
        assert result.draft == draft
        assert result.posts == [make_post()]

    def test_completedSnapshotReturnsCompletedWithoutDraft(self):
        service = AgentServices()
        payload = make_payload()
        service.graph = FakeGraph(
            {
                "thread-complete": snapshot(
                    {"payload": payload, "posts": [make_post("Final post")]}
                )
            }
        )

        result = run(service.get_thread_snapshot("thread-complete"))

        assert result.state == "completed"
        assert result.draft is None
        assert result.posts == [make_post("Final post")]

    def test_missingPayloadRaisesSnapshotError(self):
        service = AgentServices()
        service.graph = FakeGraph({"stale-thread": snapshot({"posts": []})})

        with pytest.raises(FailedToGetThreadSnapshot) as exc_info:
            run(service.get_thread_snapshot("stale-thread"))

        assert "Checkpoint missing payload" in exc_info.value.message


class TestGetStateForUserThreads:
    def test_classifiesDashboardStatusesAndSkipsMalformedCheckpoints(
        self, monkeypatch
    ):
        payload_paused = make_payload(start_date=datetime(2000, 1, 1, 9, 0))
        payload_future = make_payload(
            start_date=datetime(2999, 1, 1, 9, 0, tzinfo=timezone.utc)
        )
        payload_past = make_payload(start_date=datetime(2000, 1, 1, 9, 0))

        service = AgentServices()
        service.graph = FakeGraph(
            {
                "paused-thread": snapshot(
                    {"payload": payload_paused}, next_nodes=("Drafting",)
                ),
                "future-thread": snapshot({"payload": payload_future}),
                "past-thread": snapshot(
                    {"payload": payload_past.model_dump(mode="json")}
                ),
                "missing-payload-thread": snapshot({}),
                "bad-payload-thread": snapshot({"payload": object()}),
            }
        )

        async def get_fake_repository():
            return FakeThreadsRepository(
                [
                    "paused-thread",
                    "future-thread",
                    "past-thread",
                    "missing-payload-thread",
                    "bad-payload-thread",
                ]
            )

        monkeypatch.setattr(
            services_module,
            "get_postgres_repository_users_threads",
            get_fake_repository,
        )

        states = run(service.getStateForUserThreads("user-123"))

        assert [(state.threadId, state.status) for state in states] == [
            ("paused-thread", "Paused"),
            ("future-thread", "Assigned"),
            ("past-thread", "Completed"),
        ]
        assert states[0].campaignURL == "https://example.com/campaign"
        assert states[0].numberOfPosts == 2
