"""Regression tests for AgentServices checkpoint view helpers."""

import asyncio
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace

import pytest

from app.errorsHandler.errors import (
    FailedToGetStateForUserThreads,
    FailedToGetThreadSnapshot,
)
from app.models.AgentModels import AgentPost, AgentRunRequest, LLMPostGeneration
from app.services.AgentServices import AgentServices


def run_async(coro):
    return asyncio.run(coro)


class FakeGraph:
    def __init__(self, snapshots):
        self.snapshots = snapshots
        self.configs: list[dict] = []

    async def aget_state(self, config):
        self.configs.append(config)
        thread_id = config["configurable"]["thread_id"]
        snapshot = self.snapshots[thread_id]
        if isinstance(snapshot, BaseException):
            raise snapshot
        return snapshot


def snapshot(values, next_nodes=()):
    return SimpleNamespace(values=values, next=tuple(next_nodes))


def payload_dict(start_date: datetime):
    return {
        "userId": "user-123",
        "url": "https://example.com/docs",
        "numberOfPosts": 2,
        "startDate": start_date,
    }


class TestBuildClientView:
    def test_paused_snapshot_returns_review_state_and_serialized_draft(self):
        start_date = datetime(2026, 5, 1, 9, 0, tzinfo=timezone.utc)
        draft = {
            "content": "draft body",
            "publishDate": start_date.isoformat(),
        }
        graph = FakeGraph(
            {
                "thread-1": snapshot(
                    {
                        "payload": payload_dict(start_date),
                        "cacheDraft": draft,
                        "posts": [
                            {
                                "content": "accepted",
                                "publishDate": start_date.isoformat(),
                                "platform": "LinkedIn",
                                "postNumber": 1,
                            }
                        ],
                    },
                    next_nodes=("Drafting_And_Reviewing_Posts",),
                )
            }
        )
        service = AgentServices()

        view = run_async(
            service._buildClientView(
                graph, "thread-1", {"configurable": {"thread_id": "thread-1"}}
            )
        )

        assert view.state == "awaiting_review"
        assert view.threadId == "thread-1"
        assert view.userId == "user-123"
        assert view.draft == LLMPostGeneration.model_validate(draft)
        assert view.posts == [AgentPost.model_validate(view.posts[0])]

    def test_completed_snapshot_without_draft_returns_completed_state(self):
        start_date = datetime(2026, 5, 1, 9, 0)
        payload = AgentRunRequest.model_validate(payload_dict(start_date))
        graph = FakeGraph({"thread-1": snapshot({"payload": payload, "posts": []})})
        service = AgentServices()

        view = run_async(
            service._buildClientView(
                graph, "thread-1", {"configurable": {"thread_id": "thread-1"}}
            )
        )

        assert view.state == "completed"
        assert view.draft is None
        assert view.startDate == start_date

    def test_missing_payload_raises_value_error(self):
        graph = FakeGraph({"thread-1": snapshot({"posts": []})})
        service = AgentServices()

        with pytest.raises(ValueError, match="Checkpoint missing payload"):
            run_async(
                service._buildClientView(
                    graph, "thread-1", {"configurable": {"thread_id": "thread-1"}}
                )
            )


class TestThreadSnapshot:
    def test_missing_payload_is_wrapped_as_failed_thread_snapshot(self):
        service = AgentServices()
        service.graph = FakeGraph({"thread-1": snapshot({})})

        with pytest.raises(FailedToGetThreadSnapshot, match="Checkpoint missing payload"):
            run_async(service.get_thread_snapshot("thread-1"))


class TestGetStateForUserThreads:
    def test_classifies_paused_assigned_completed_and_skips_bad_checkpoints(
        self, monkeypatch
    ):
        now = datetime.now(timezone.utc)
        service = AgentServices()
        service.graph = FakeGraph(
            {
                "paused": snapshot(
                    {"payload": payload_dict(now - timedelta(hours=1))},
                    next_nodes=("Drafting_And_Reviewing_Posts",),
                ),
                "assigned": snapshot(
                    {"payload": payload_dict(now + timedelta(days=2))}
                ),
                "completed": snapshot(
                    {"payload": payload_dict(now - timedelta(days=2))}
                ),
                "missing-payload": snapshot({}),
                "bad-payload": snapshot({"payload": "unexpected"}),
            }
        )

        class FakeThreadRepo:
            async def getThreads(self, user_id):
                assert user_id == "user-123"
                return [
                    ("paused",),
                    ("assigned",),
                    ("completed",),
                    ("missing-payload",),
                    ("bad-payload",),
                ]

        async def fake_repo():
            return FakeThreadRepo()

        monkeypatch.setattr(
            "app.services.AgentServices.get_postgres_repository_users_threads",
            fake_repo,
        )

        states = run_async(service.getStateForUserThreads("user-123"))

        assert [(state.threadId, state.status) for state in states] == [
            ("paused", "Paused"),
            ("assigned", "Assigned"),
            ("completed", "Completed"),
        ]
        assert [cfg["configurable"]["thread_id"] for cfg in service.graph.configs] == [
            "paused",
            "assigned",
            "completed",
            "missing-payload",
            "bad-payload",
        ]

    def test_snapshot_errors_are_wrapped(self, monkeypatch):
        service = AgentServices()
        service.graph = FakeGraph({"broken": RuntimeError("checkpoint down")})

        class FakeThreadRepo:
            async def getThreads(self, user_id):
                return [("broken",)]

        async def fake_repo():
            return FakeThreadRepo()

        monkeypatch.setattr(
            "app.services.AgentServices.get_postgres_repository_users_threads",
            fake_repo,
        )

        with pytest.raises(FailedToGetStateForUserThreads, match="checkpoint down"):
            run_async(service.getStateForUserThreads("user-123"))
