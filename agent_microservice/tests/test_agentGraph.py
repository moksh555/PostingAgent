"""Deterministic tests for current `app.services.agentGraph` node contracts."""

import asyncio
from datetime import datetime
from types import SimpleNamespace

import pytest

from app.errorsHandler.errors import (
    FailedToBuildMarketingBriefError,
    FailedToBuildPosts,
    NoPayloadError,
)
from app.models.AgentModels import (
    AgentSummary,
    LLMPostGeneration,
)
from app.services import agentGraph as AG


LONG_POST = (
    "A practical launch update for operators who need clearer planning, faster "
    "execution, and reliable follow-through across every campaign touchpoint."
)


def run(coro):
    return asyncio.run(coro)


# --------------------------------------------------------------------------- #
#  receiverNode                                                               #
# --------------------------------------------------------------------------- #


class TestReceiverNode:
    def test_happyPathPersistsThreadForUser(self, samplePayload, monkeypatch):
        calls = []

        class FakeRepository:
            async def saveThreadIdForUser(self, user_id, thread_id):
                calls.append((user_id, thread_id))

        async def get_fake_repository():
            return FakeRepository()

        runtime = SimpleNamespace(
            execution_info=SimpleNamespace(thread_id="thread-123")
        )
        monkeypatch.setattr(AG, "get_postgres_repository_posts", get_fake_repository)

        assert run(AG.receiverNode({"payload": samplePayload}, runtime)) == {}
        assert calls == [("user-123", "thread-123")]

    def test_raisesWhenPayloadMissing(self):
        with pytest.raises(NoPayloadError):
            run(AG.receiverNode({}, SimpleNamespace()))


# --------------------------------------------------------------------------- #
#  Routers                                                                    #
# --------------------------------------------------------------------------- #


class TestRoutingGeneratePostsNode:
    def test_regenerateTruthyRoutesToRegen(self, samplePayload):
        state = {
            "regeneratePost": True,
            "payload": samplePayload,
            "currentLoopStartNumber": 0,
        }
        assert AG.routingGneratePostsNode(state) == "Regenerating_With_Feedback"

    def test_moreSlotsRemainingRoutesBackToGen(self, multiPostPayload):
        state = {
            "regeneratePost": False,
            "payload": multiPostPayload,
            "currentLoopStartNumber": 1,
        }
        assert AG.routingGneratePostsNode(state) == "Drafting_And_Reviewing_Posts"

    def test_allSlotsDoneRoutesToPersistence(self, samplePayload):
        state = {
            "regeneratePost": False,
            "payload": samplePayload,
            "currentLoopStartNumber": 1,
        }
        assert AG.routingGneratePostsNode(state) == "Saving_Data_To_Database"

    def test_noneCounterTreatedAsZero(self, samplePayload):
        state = {"regeneratePost": False, "payload": samplePayload}
        assert AG.routingGneratePostsNode(state) == "Drafting_And_Reviewing_Posts"


class TestRoutingRegeneratePostsNode:
    def test_regenerateFalsyReturnsToGen(self):
        assert (
            AG.routingReGneratePostsNode({"regeneratePost": False})
            == "Drafting_And_Reviewing_Posts"
        )

    def test_regenerateTruthyStaysInRegen(self):
        assert (
            AG.routingReGneratePostsNode({"regeneratePost": True})
            == "Regenerating_With_Feedback"
        )


# --------------------------------------------------------------------------- #
#  buildingMarketingBrief                                                     #
# --------------------------------------------------------------------------- #


class TestBuildingMarketingBrief:
    def test_happyPathReturnsNotes(self, samplePayload, monkeypatch):
        fakeSummary = AgentSummary(marketingBrief="A real brief.", fileName="t.txt")

        async def fake_tool_loop(*args, **kwargs):
            return fakeSummary

        monkeypatch.setattr(AG, "_ainvoke_update_llm_with_tool_loop", fake_tool_loop)

        result = run(AG.buildingMarketingBrief({"payload": samplePayload}))
        assert result == {"notes": fakeSummary}

    def test_emptyBriefRaises(self, samplePayload, monkeypatch):
        fakeSummary = AgentSummary(marketingBrief="", fileName="t.txt")

        async def fake_tool_loop(*args, **kwargs):
            return fakeSummary

        monkeypatch.setattr(AG, "_ainvoke_update_llm_with_tool_loop", fake_tool_loop)

        with pytest.raises(FailedToBuildMarketingBriefError):
            run(AG.buildingMarketingBrief({"payload": samplePayload}))


# --------------------------------------------------------------------------- #
#  generatingMarketingPosts — produce-step only                               #
# --------------------------------------------------------------------------- #


class TestGeneratingMarketingPostsProduce:
    def _baseState(self, payload):
        return {
            "payload": payload,
            "notes": AgentSummary(marketingBrief="notes", fileName="brief.txt"),
            "posts": [],
            "currentLoopStartNumber": 0,
            "cacheDraft": None,
            "currentFeedback": [],
        }

    def test_producesDraftAndWritesCache(self, samplePayload, monkeypatch):
        draft = LLMPostGeneration(
            content=LONG_POST, publishDate=datetime(2026, 5, 1, 9, 0)
        )

        async def fake_tool_loop(*args, **kwargs):
            return draft

        monkeypatch.setattr(AG, "_ainvoke_update_llm_with_tool_loop", fake_tool_loop)

        result = run(AG.generatingMarketingPosts(self._baseState(samplePayload)))

        assert result["cacheDraft"] == draft

    def test_emptyContentRaisesFailedToBuildPosts(
        self, samplePayload, monkeypatch
    ):
        draft = LLMPostGeneration(content="", publishDate=datetime(2026, 5, 1, 9, 0))

        async def fake_tool_loop(*args, **kwargs):
            return draft

        monkeypatch.setattr(AG, "_ainvoke_update_llm_with_tool_loop", fake_tool_loop)

        with pytest.raises(FailedToBuildPosts):
            run(AG.generatingMarketingPosts(self._baseState(samplePayload)))


# --------------------------------------------------------------------------- #
#  regeneratePost — produce-step only                                         #
# --------------------------------------------------------------------------- #


class TestRegeneratePostProduce:
    def _baseState(self, payload):
        original = LLMPostGeneration(
            content=LONG_POST, publishDate=datetime(2026, 5, 1, 9, 0)
        )
        return {
            "payload": payload,
            "notes": AgentSummary(marketingBrief="notes", fileName="brief.txt"),
            "posts": [],
            "postToRegenerate": original,
            "postRegenerationDescription": "make it shorter",
            "cacheDraft": None,
            "currentFeedback": [],
        }

    def test_producesRegenDraftAndWritesCache(
        self, samplePayload, monkeypatch
    ):
        revised = LLMPostGeneration(
            content=LONG_POST + " Revised.", publishDate=datetime(2026, 5, 1, 9, 0)
        )

        async def fake_tool_loop(*args, **kwargs):
            return revised

        monkeypatch.setattr(AG, "_ainvoke_update_llm_with_tool_loop", fake_tool_loop)

        result = run(AG.regeneratePost(self._baseState(samplePayload)))

        assert result == {"cacheDraft": revised}

    def test_emptyContentRaisesFailedToBuildPosts(
        self, samplePayload, monkeypatch
    ):
        empty = LLMPostGeneration(content="", publishDate=datetime(2026, 5, 1, 9, 0))

        async def fake_tool_loop(*args, **kwargs):
            return empty

        monkeypatch.setattr(AG, "_ainvoke_update_llm_with_tool_loop", fake_tool_loop)

        with pytest.raises(FailedToBuildPosts):
            run(AG.regeneratePost(self._baseState(samplePayload)))


class TestAggregateSummary:
    def test_reportsAggregatedOnlyWhenBothUpdatesCompleted(self):
        assert run(
            AG.aggregateSummary(
                {"updatedCurrentFeedback": True, "updatedPreviousSummary": True}
            )
        ) == {"aggregatedSummary": True}
        assert run(
            AG.aggregateSummary(
                {"updatedCurrentFeedback": True, "updatedPreviousSummary": False}
            )
        ) == {"aggregatedSummary": False}
