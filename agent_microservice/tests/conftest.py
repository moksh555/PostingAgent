"""Shared fixtures for the agent graph test suite.

Configuration-backed modules instantiate their clients at import time, so tests
provide local defaults before importing application code. The real Gemini, S3,
and Postgres services are never contacted by the unit tests.
"""

import os

os.environ.setdefault("PORT", "8000")
os.environ.setdefault("GEMINI_API_KEY", "test-key-unused-because-we-mock")
os.environ.setdefault("POSTGRES_DB_URI", "postgresql://test:test@localhost:5432/test")
os.environ.setdefault("AWS_ACCESS_KEY_ID", "test")
os.environ.setdefault("AWS_SECRET_ACCESS_KEY", "test")
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
