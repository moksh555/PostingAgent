"""Tests for `app.services.agentGraph`.

Strategy (see feature.md §12.3):
    1. Cheapest first — validator + router unit tests (pure functions).
    2. Individual node unit tests with hand-crafted AgentState dicts.
    3. End-to-end tests that compile+invoke the graph and drive HITL via
       `Command(resume=...)`. These also carry the replay-safety canary.

All LLM calls are replaced with `RunnableLambda`-based fakes built by the
`makeFakeLLM` fixture from conftest. The real Gemini API is never hit.
"""

from datetime import datetime
from unittest.mock import MagicMock

import pytest
from langgraph.graph import END  # type: ignore
from langgraph.types import Command  # type: ignore

from app.errorsHandler import (
    FailedToBuildMarketingBriefError,
    FailedToBuildPosts,
    NoPayloadError,
)
from app.models.AgentModels import (
    AgentPostGenerationInterrupt,
    AgentSummary,
    LLMPostGeneration,
)
from app.services import agentGraph as AG


# --------------------------------------------------------------------------- #
#  receiverNode                                                               #
# --------------------------------------------------------------------------- #


class TestReceiverNode:
    def test_happyPathReturnsPayload(self, samplePayload):
        assert AG.receiverNode({"payload": samplePayload}) == {"payload": samplePayload}

    def test_raisesWhenPayloadMissing(self):
        with pytest.raises(NoPayloadError):
            AG.receiverNode({})


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

    def test_allSlotsDoneRoutesToEnd(self, samplePayload):
        state = {
            "regeneratePost": False,
            "payload": samplePayload,
            "currentLoopStartNumber": 1,
        }
        assert AG.routingGneratePostsNode(state) == END

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
    def test_happyPathReturnsNotes(self, samplePayload, makeFakeLLM, monkeypatch):
        fakeSummary = AgentSummary(marketingBrief="A real brief.", fileName="t.txt")
        monkeypatch.setattr(AG, "structuredSummaryLLM", makeFakeLLM([fakeSummary]))

        result = AG.buildingMarketingBrief({"payload": samplePayload})
        assert result == {"marketingNotes": "A real brief."}

    def test_emptyBriefRaises(self, samplePayload, makeFakeLLM, monkeypatch):
        fakeSummary = AgentSummary(marketingBrief="", fileName="t.txt")
        monkeypatch.setattr(AG, "structuredSummaryLLM", makeFakeLLM([fakeSummary]))

        with pytest.raises(FailedToBuildMarketingBriefError):
            AG.buildingMarketingBrief({"payload": samplePayload})


# --------------------------------------------------------------------------- #
#  generatingMarketingPosts — produce-step only                               #
#                                                                             #
#  The review step calls `interrupt(...)` which only works through the        #
#  compiled graph runtime; see TestEndToEnd for those paths.                  #
# --------------------------------------------------------------------------- #


class TestGeneratingMarketingPostsProduce:
    def _baseState(self, payload):
        return {
            "payload": payload,
            "marketingNotes": "notes",
            "posts": [],
            "currentLoopStartNumber": 0,
            "cacheDraft": None,
        }

    def test_producesDraftAndWritesCache(self, samplePayload, makeFakeLLM, monkeypatch):
        draft = LLMPostGeneration(
            content="hello", publishDate=datetime(2026, 5, 1, 9, 0)
        )
        monkeypatch.setattr(AG, "structuredPostGenerationLLM", makeFakeLLM([draft]))

        result = AG.generatingMarketingPosts(
            self._baseState(samplePayload), MagicMock()
        )

        assert result["cacheDraft"] == draft
        assert result["posts"] == []

    def test_emptyContentRaisesFailedToBuildPosts(
        self, samplePayload, makeFakeLLM, monkeypatch
    ):
        draft = LLMPostGeneration(content="", publishDate=datetime(2026, 5, 1, 9, 0))
        monkeypatch.setattr(AG, "structuredPostGenerationLLM", makeFakeLLM([draft]))

        with pytest.raises(FailedToBuildPosts):
            AG.generatingMarketingPosts(self._baseState(samplePayload), MagicMock())


# --------------------------------------------------------------------------- #
#  regeneratePost — produce-step only                                         #
# --------------------------------------------------------------------------- #


class TestRegeneratePostProduce:
    def _baseState(self, payload):
        original = LLMPostGeneration(
            content="v1", publishDate=datetime(2026, 5, 1, 9, 0)
        )
        return {
            "payload": payload,
            "marketingNotes": "notes",
            "posts": [],
            "postToRegenerate": original,
            "postRegenerationDescription": "make it shorter",
            "cacheDraft": None,
        }

    def test_producesRegenDraftAndWritesCache(
        self, samplePayload, makeFakeLLM, monkeypatch
    ):
        revised = LLMPostGeneration(
            content="v2", publishDate=datetime(2026, 5, 1, 9, 0)
        )
        monkeypatch.setattr(AG, "structuredPostGenerationLLM", makeFakeLLM([revised]))

        result = AG.regeneratePost(self._baseState(samplePayload), MagicMock())

        assert result == {"cacheDraft": revised}

    def test_emptyContentRaisesFailedToBuildPosts(
        self, samplePayload, makeFakeLLM, monkeypatch
    ):
        empty = LLMPostGeneration(content="", publishDate=datetime(2026, 5, 1, 9, 0))
        monkeypatch.setattr(AG, "structuredPostGenerationLLM", makeFakeLLM([empty]))

        with pytest.raises(FailedToBuildPosts):
            AG.regeneratePost(self._baseState(samplePayload), MagicMock())


# --------------------------------------------------------------------------- #
#  End-to-end flow through the compiled graph                                 #
# --------------------------------------------------------------------------- #


class TestEndToEnd:
    """Exercise the compiled graph with a real checkpointer and HITL resumes."""

    def _patchLLMs(
        self,
        monkeypatch,
        makeFakeLLM,
        briefResponses,
        postResponses,
        postCalls=None,
    ):
        monkeypatch.setattr(AG, "structuredSummaryLLM", makeFakeLLM(briefResponses))
        monkeypatch.setattr(
            AG,
            "structuredPostGenerationLLM",
            makeFakeLLM(postResponses, calls=postCalls),
        )

    def _assertGraphPaused(self, config):
        snapshot = AG.graph.get_state(config)
        assert snapshot.next, "Graph was expected to be paused at an interrupt"

    # ---------- happy path ---------- #

    def test_singlePostAcceptProducesFinalPost(
        self, samplePayload, makeFakeLLM, monkeypatch, newThreadConfig
    ):
        draft = LLMPostGeneration(
            content="post body", publishDate=datetime(2026, 5, 1, 9, 0)
        )
        self._patchLLMs(
            monkeypatch,
            makeFakeLLM,
            briefResponses=[AgentSummary(marketingBrief="brief", fileName="t.txt")],
            postResponses=[draft],
        )

        AG.graph.invoke({"payload": samplePayload}, config=newThreadConfig)
        self._assertGraphPaused(newThreadConfig)

        final = AG.graph.invoke(
            Command(resume=AgentPostGenerationInterrupt(actions="Accept")),
            config=newThreadConfig,
        )

        posts = final["posts"]
        assert len(posts) == 1
        assert posts[0].content == "post body"
        assert posts[0].platform == "LinkedIn"
        assert posts[0].postNumber == 1

    # ---------- replay-safety canary (see PROGRESS.md Stage 19) ---------- #

    def test_cacheDraftPreventsDoubleLLMCallOnResume(
        self, samplePayload, makeFakeLLM, monkeypatch, newThreadConfig
    ):
        """LLM must be called exactly once per draft, regardless of node replays."""
        calls: list = []
        draft = LLMPostGeneration(
            content="body", publishDate=datetime(2026, 5, 1, 9, 0)
        )
        self._patchLLMs(
            monkeypatch,
            makeFakeLLM,
            briefResponses=[AgentSummary(marketingBrief="brief", fileName="t.txt")],
            postResponses=[draft],
            postCalls=calls,
        )

        AG.graph.invoke({"payload": samplePayload}, config=newThreadConfig)
        AG.graph.invoke(
            Command(resume=AgentPostGenerationInterrupt(actions="Accept")),
            config=newThreadConfig,
        )

        assert len(calls) == 1, (
            f"Expected 1 post-LLM call, got {len(calls)}. "
            "cacheDraft is not protecting replays."
        )

    # ---------- regenerate -> accept ---------- #

    def test_regenerateThenAcceptFlow(
        self, samplePayload, makeFakeLLM, monkeypatch, newThreadConfig
    ):
        originalDraft = LLMPostGeneration(
            content="v1", publishDate=datetime(2026, 5, 1, 9, 0)
        )
        revisedDraft = LLMPostGeneration(
            content="v2", publishDate=datetime(2026, 5, 1, 9, 0)
        )
        self._patchLLMs(
            monkeypatch,
            makeFakeLLM,
            briefResponses=[AgentSummary(marketingBrief="brief", fileName="t.txt")],
            postResponses=[originalDraft, revisedDraft],
        )

        AG.graph.invoke({"payload": samplePayload}, config=newThreadConfig)
        self._assertGraphPaused(newThreadConfig)

        AG.graph.invoke(
            Command(
                resume=AgentPostGenerationInterrupt(
                    actions="Regenerate",
                    postChangeDescription="shorter, more casual",
                )
            ),
            config=newThreadConfig,
        )
        self._assertGraphPaused(newThreadConfig)

        final = AG.graph.invoke(
            Command(resume=AgentPostGenerationInterrupt(actions="Accept")),
            config=newThreadConfig,
        )

        posts = final["posts"]
        assert len(posts) == 1
        assert posts[0].content == "v2"

    # ---------- reject skips the slot ---------- #

    def test_rejectSkipsSlotAndEndsWithNoPosts(
        self, samplePayload, makeFakeLLM, monkeypatch, newThreadConfig
    ):
        draft = LLMPostGeneration(
            content="body", publishDate=datetime(2026, 5, 1, 9, 0)
        )
        self._patchLLMs(
            monkeypatch,
            makeFakeLLM,
            briefResponses=[AgentSummary(marketingBrief="brief", fileName="t.txt")],
            postResponses=[draft],
        )

        AG.graph.invoke({"payload": samplePayload}, config=newThreadConfig)
        final = AG.graph.invoke(
            Command(resume=AgentPostGenerationInterrupt(actions="Reject")),
            config=newThreadConfig,
        )

        assert final.get("posts") in (None, [])
