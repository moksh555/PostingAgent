"""Shared fixtures for the agent test suite.

Config defaults must be set before any app modules are imported because the
settings object and Gemini clients are created at module import time. Tests
patch graph/service collaborators, so these values are never used externally.
"""

import os

os.environ.setdefault("GEMINI_API_KEY", "test-key-unused-because-we-mock")
os.environ.setdefault("PORT", "8000")
os.environ.setdefault("POSTGRES_DB_URI", "postgresql://user:pass@localhost:5432/test")
os.environ.setdefault("AWS_ACCESS_KEY_ID", "test-access-key")
os.environ.setdefault("AWS_SECRET_ACCESS_KEY", "test-secret-key")
os.environ.setdefault("AWS_DEFAULT_REGION", "us-east-1")
os.environ.setdefault("AWS_BUCKET_NAME", "test-bucket")

import uuid
from datetime import datetime
from typing import Any, Iterable

import pytest
from langchain_core.runnables import RunnableLambda  # type: ignore


@pytest.fixture
def samplePayload():
    from app.models.AgentModels import AgentRunRequest

    return AgentRunRequest(
        userId="user-123",
        url="https://example.com/docs",
        numberOfPosts=1,
        startDate=datetime(2026, 5, 1, 9, 0),
    )


@pytest.fixture
def multiPostPayload():
    from app.models.AgentModels import AgentRunRequest

    return AgentRunRequest(
        userId="user-123",
        url="https://example.com/docs",
        numberOfPosts=3,
        startDate=datetime(2026, 5, 1, 9, 0),
    )


@pytest.fixture
def makeFakeLLM():
    """Factory fixture. Returns a callable `(responses, calls=None) -> Runnable`.

    `responses` is the ordered queue of return values; an item that is an
    Exception instance is raised instead of returned. If `calls` (a list) is
    supplied, each invocation appends its input so tests can assert call count.
    """

    def build(responses: Iterable[Any], calls: list | None = None):
        queue = list(responses)
        cursor = {"i": 0}

        def fn(inputValue):
            if calls is not None:
                calls.append(inputValue)
            i = cursor["i"]
            if i >= len(queue):
                raise AssertionError("FakeLLM queue exhausted")
            cursor["i"] += 1
            value = queue[i]
            if isinstance(value, BaseException):
                raise value
            return value

        return RunnableLambda(fn)

    return build


@pytest.fixture
def newThreadConfig():
    """A LangGraph config dict with a fresh thread_id per test."""
    return {"configurable": {"thread_id": str(uuid.uuid4())}}
