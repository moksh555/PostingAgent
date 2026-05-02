"""Shared fixtures for the agent graph test suite.

We set GEMINI_API_KEY *before* any app modules are imported. The module-level
`ChatGoogleGenerativeAI(google_api_key=config.GEMINI_API_KEY)` construction
would otherwise fail at import time. We never hit the real Gemini API — every
test patches the two module-level LLM singletons with RunnableLambda fakes.
"""

import os

os.environ.setdefault("GEMINI_API_KEY", "test-key-unused-because-we-mock")

import uuid
from datetime import datetime
from typing import Any, Iterable

import pytest
from langchain_core.runnables import RunnableLambda  # type: ignore


@pytest.fixture(autouse=True)
def noWritesToDisk(monkeypatch):
    """Stop buildingMarketingBrief from writing to Backend/testSummary/."""
    from app.services import agentGraph as AG

    monkeypatch.setattr(AG, "writeSummaryToFile", lambda response: None)


@pytest.fixture
def samplePayload():
    from app.models.AgentModels import AgentRunRequest

    return AgentRunRequest(
        url="https://example.com/docs",
        numberOfPosts=1,
        startDate=datetime(2026, 5, 1, 9, 0),
    )


@pytest.fixture
def multiPostPayload():
    from app.models.AgentModels import AgentRunRequest

    return AgentRunRequest(
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
