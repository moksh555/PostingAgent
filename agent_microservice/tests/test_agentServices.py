"""Tests for client-facing agent service view/state helpers."""

import asyncio
import importlib
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace

import pytest

from app.errorsHandler.errors import FailedToGetStateForUserThreads, FailedToGetThreads
from app.models.AgentModels import AgentPost, AgentRunRequest, LLMPostGeneration
from app.services.AgentServices import AgentServices

AS_MODULE = importlib.import_module("app.services.AgentServices")


def run(coro):
    return asyncio.run(coro)


class FakeGraph:
    def __init__(self, snapshots):
        self.snapshots = snapshots
        self.configs = []

    async def aget_state(self, config):
        self.configs.append(config)
        thread_id = config["configurable"]["thread_id"]
        return self.snapshots[thread_id]


def snapshot(values, next_nodes=()):
    return SimpleNamespace(values=values, next=next_nodes)


def payload(start_date=None):
    return AgentRunRequest(
        userId="user-123",
        url="https://example.com/campaign",
        numberOfPosts=2,
        startDate=start_date or datetime(2026, 5, 1, 9, 0, tzinfo=timezone.utc),
    )


def post_dict(number=1):
    return {
        "content": "approved post",
        "publishDate": datetime(2026, 5, 2, 9, 0, tzinfo=timezone.utc),
        "platform": "LinkedIn",
        "postNumber": number,
    }


class TestBuildClientView:
    def test_paused_snapshot_serializes_dict_payload_posts_and_cache_draft(self):
        service = AgentServices()
        draft = {
            "content": "draft post",
            "publishDate": datetime(2026, 5, 3, 9, 0, tzinfo=timezone.utc),
        }
        graph = FakeGraph(
            {
                "thread-1": snapshot(
                    {
                        "payload": payload().model_dump(mode="json"),
                        "posts": [post_dict()],
                        "cacheDraft": draft,
                    }
                )
            }
        )

        view = run(
            service._buildClientView(
                graph, "thread-1", {"configurable": {"thread_id": "thread-1"}}
            )
        )

        assert view.state == "awaiting_review"
        assert view.threadId == "thread-1"
        assert view.userId == "user-123"
        assert view.posts == [AgentPost.model_validate(post_dict())]
        assert view.draft == LLMPostGeneration.model_validate(draft)

    def test_snapshot_next_marks_review_even_without_cached_draft(self):
        service = AgentServices()
        graph = FakeGraph(
            {
                "thread-1": snapshot(
                    {"payload": payload(), "posts": [post_dict()], "cacheDraft": None},
                    next_nodes=("Drafting_And_Reviewing_Posts",),
                )
            }
        )

        view = run(
            service._buildClientView(
                graph, "thread-1", {"configurable": {"thread_id": "thread-1"}}
            )
        )

        assert view.state == "awaiting_review"
        assert view.draft is None

    def test_completed_snapshot_has_completed_state(self):
        service = AgentServices()
        graph = FakeGraph(
            {
                "thread-1": snapshot(
                    {"payload": payload(), "posts": [post_dict()], "cacheDraft": None}
                )
            }
        )

        view = run(
            service._buildClientView(
                graph, "thread-1", {"configurable": {"thread_id": "thread-1"}}
            )
        )

        assert view.state == "completed"
        assert view.draft is None
        assert view.posts[0].postNumber == 1

    def test_missing_payload_raises_clear_checkpoint_error(self):
        service = AgentServices()
        graph = FakeGraph({"thread-1": snapshot({"posts": []})})

        with pytest.raises(ValueError, match="Checkpoint missing payload"):
            run(
                service._buildClientView(
                    graph, "thread-1", {"configurable": {"thread_id": "thread-1"}}
                )
            )


class TestGetStateForUserThreads:
    class FakeThreadRepository:
        def __init__(self, threads=None, error=None):
            self.threads = threads or []
            self.error = error
            self.user_ids = []

        async def getThreads(self, user_id):
            if self.error:
                raise self.error
            self.user_ids.append(user_id)
            return self.threads

    def test_classifies_paused_assigned_completed_and_skips_bad_checkpoints(
        self, monkeypatch
    ):
        now = datetime.now(timezone.utc)
        graph = FakeGraph(
            {
                "paused": snapshot(
                    {"payload": payload(now - timedelta(days=1))},
                    next_nodes=("Drafting_And_Reviewing_Posts",),
                ),
                "assigned": snapshot({"payload": payload(now + timedelta(days=1))}),
                "completed": snapshot({"payload": payload(now - timedelta(days=1))}),
                "missing": snapshot({}),
                "invalid": snapshot({"payload": {"url": "not-a-url"}}),
            }
        )
        repo = self.FakeThreadRepository(
            [
                ("paused",),
                ("assigned",),
                ("completed",),
                ("missing",),
                ("invalid",),
            ]
        )

        async def fake_repo():
            return repo

        monkeypatch.setattr(
            AS_MODULE, "get_postgres_repository_users_threads", fake_repo
        )
        service = AgentServices()
        service.graph = graph

        states = run(service.getStateForUserThreads("user-123"))

        assert repo.user_ids == ["user-123"]
        assert [(state.threadId, state.status) for state in states] == [
            ("paused", "Paused"),
            ("assigned", "Assigned"),
            ("completed", "Completed"),
        ]
        assert graph.configs == [
            {"configurable": {"thread_id": "paused"}},
            {"configurable": {"thread_id": "assigned"}},
            {"configurable": {"thread_id": "completed"}},
            {"configurable": {"thread_id": "missing"}},
            {"configurable": {"thread_id": "invalid"}},
        ]

    def test_thread_repository_domain_error_propagates(self, monkeypatch):
        async def fake_repo():
            return self.FakeThreadRepository(error=FailedToGetThreads("db failed"))

        monkeypatch.setattr(
            AS_MODULE, "get_postgres_repository_users_threads", fake_repo
        )
        service = AgentServices()
        service.graph = FakeGraph({})

        with pytest.raises(FailedToGetThreads):
            run(service.getStateForUserThreads("user-123"))

    def test_unexpected_graph_error_is_wrapped(self, monkeypatch):
        async def fake_repo():
            return self.FakeThreadRepository(threads=[("missing-snapshot",)])

        monkeypatch.setattr(
            AS_MODULE, "get_postgres_repository_users_threads", fake_repo
        )
        service = AgentServices()
        service.graph = FakeGraph({})

        with pytest.raises(FailedToGetStateForUserThreads, match="missing-snapshot"):
            run(service.getStateForUserThreads("user-123"))
