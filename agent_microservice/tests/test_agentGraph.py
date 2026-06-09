"""Focused regression tests for the current async agent graph helpers.

These tests isolate LangGraph node behavior from real Gemini, Postgres, and S3
services while covering the recent tool-loop and persistence setup changes.
"""

import asyncio
from datetime import datetime
from types import SimpleNamespace

import pytest
from langchain_core.messages import ToolMessage  # type: ignore

from app.errorsHandler.errors import (
    FailedToBuildContext,
    FailedToBuildMarketingBriefError,
    FailedToBuildPosts,
    FailedToSaveThreadIdForUser,
    NoPayloadError,
    NoUserIdError,
)
from app.models.AgentModels import AgentSummary, LLMPostGeneration
from app.services import agentGraph as AG


LONG_POST = (
    "This launch post gives product teams a practical way to plan, review, "
    "and publish stronger marketing updates with clearer context, approvals, "
    "and scheduling discipline across every campaign."
)


def run(coro):
    return asyncio.run(coro)


class TestToolLoop:
    class FakeTool:
        def __init__(self, response):
            self.response = response
            self.calls = []

        async def ainvoke(self, args):
            self.calls.append(args)
            return self.response

    class FakeModel:
        def __init__(self, responses):
            self.responses = list(responses)
            self.messages_seen = []

        async def ainvoke(self, messages):
            self.messages_seen.append(list(messages))
            if not self.responses:
                raise AssertionError("Fake model exhausted")
            return self.responses.pop(0)

    def test_executes_tool_calls_until_final_response(self, monkeypatch):
        tool = self.FakeTool(response={"exists": True})
        first_ai = SimpleNamespace(
            tool_calls=[
                {
                    "name": "check_if_file_exists_S3",
                    "args": {"key": "UserNotes/user-123/knowledge/previous_summary.txt"},
                    "id": "call-1",
                }
            ]
        )
        final = AgentSummary(marketingBrief="brief", fileName="brief.txt")
        model = self.FakeModel([first_ai, final])
        monkeypatch.setattr(AG, "check_if_file_exists_S3", tool)

        result = run(
            AG._ainvoke_update_llm_with_tool_loop(
                model,
                "system",
                "user",
            )
        )

        assert result == final
        assert tool.calls == [
            {"key": "UserNotes/user-123/knowledge/previous_summary.txt"}
        ]
        second_round_messages = model.messages_seen[1]
        assert any(
            isinstance(message, ToolMessage)
            and message.content == "{'exists': True}"
            and message.tool_call_id == "call-1"
            for message in second_round_messages
        )

    def test_unknown_tool_call_fails_fast(self):
        model = self.FakeModel(
            [SimpleNamespace(tool_calls=[{"name": "delete_everything", "args": {}}])]
        )

        with pytest.raises(ValueError, match="Unknown tool requested: delete_everything"):
            run(AG._ainvoke_update_llm_with_tool_loop(model, "system", "user"))

    def test_max_tool_rounds_prevents_infinite_loop(self, monkeypatch):
        model = self.FakeModel(
            [
                SimpleNamespace(
                    tool_calls=[
                        {
                            "name": "check_if_file_exists_S3",
                            "args": {"key": "same-key"},
                            "id": "call-1",
                        }
                    ]
                )
                for _ in range(2)
            ]
        )
        monkeypatch.setattr(AG, "check_if_file_exists_S3", self.FakeTool(False))

        with pytest.raises(ValueError, match="Model did not finish after 2 tool rounds"):
            run(
                AG._ainvoke_update_llm_with_tool_loop(
                    model,
                    "system",
                    "user",
                    max_tool_rounds=2,
                )
            )


class TestReceiverNode:
    class FakePostgresRepository:
        def __init__(self, error=None):
            self.saved = []
            self.error = error

        async def saveThreadIdForUser(self, user_id, thread_id):
            if self.error:
                raise self.error
            self.saved.append((user_id, thread_id))

    @staticmethod
    def runtime(thread_id="thread-123"):
        return SimpleNamespace(execution_info=SimpleNamespace(thread_id=thread_id))

    def test_saves_user_thread_mapping(self, samplePayload, monkeypatch):
        repo = self.FakePostgresRepository()

        async def fake_repo():
            return repo

        monkeypatch.setattr(AG, "get_postgres_repository_posts", fake_repo)

        assert run(AG.receiverNode({"payload": samplePayload}, self.runtime())) == {}
        assert repo.saved == [("user-123", "thread-123")]

    def test_missing_payload_and_user_id_are_rejected(self, samplePayload):
        with pytest.raises(NoPayloadError):
            run(AG.receiverNode({}, self.runtime()))

        with pytest.raises(NoUserIdError):
            run(
                AG.receiverNode(
                    {"payload": samplePayload.model_copy(update={"userId": None})},
                    self.runtime(),
                )
            )

    def test_repository_failure_propagates_domain_error(self, samplePayload, monkeypatch):
        expected = FailedToSaveThreadIdForUser("database unavailable")

        async def fake_repo():
            return self.FakePostgresRepository(error=expected)

        monkeypatch.setattr(AG, "get_postgres_repository_posts", fake_repo)

        with pytest.raises(FailedToSaveThreadIdForUser) as exc_info:
            run(AG.receiverNode({"payload": samplePayload}, self.runtime()))
        assert exc_info.value is expected


class TestBuildingContext:
    class FakeS3:
        def __init__(self, exists_by_key=None, error=None):
            self.exists_by_key = exists_by_key or {}
            self.error = error
            self.checked = []
            self.puts = []

        async def check_if_file_exists(self, bucketName, key):
            if self.error:
                raise self.error
            self.checked.append((bucketName, key))
            return self.exists_by_key.get(key, False)

        async def put_object(self, body, bucketName, key):
            self.puts.append((body, bucketName, key))
            return True

    def test_creates_only_missing_knowledge_placeholders(self, samplePayload, monkeypatch):
        previous_key = "UserNotes/user-123/knowledge/previous_summary.txt"
        feedback_key = "UserNotes/user-123/knowledge/feedback_summary.txt"
        s3 = self.FakeS3(exists_by_key={previous_key: False, feedback_key: True})
        monkeypatch.setattr(AG, "get_s3_connection", lambda: s3)
        monkeypatch.setattr(AG.config, "AWS_BUCKET_NAME", "bucket")

        assert run(AG.buildingContext({"payload": samplePayload})) == {}
        assert s3.checked == [("bucket", previous_key), ("bucket", feedback_key)]
        assert s3.puts == [("", "bucket", previous_key)]

    def test_s3_failure_is_wrapped(self, samplePayload, monkeypatch):
        monkeypatch.setattr(
            AG, "get_s3_connection", lambda: self.FakeS3(error=RuntimeError("boom"))
        )

        with pytest.raises(FailedToBuildContext, match="boom"):
            run(AG.buildingContext({"payload": samplePayload}))


class TestBuildingMarketingBrief:
    def test_uses_tool_loop_and_validates_structured_response(
        self, samplePayload, monkeypatch
    ):
        calls = []
        summary = AgentSummary(marketingBrief="A useful brief.", fileName="brief.txt")

        async def fake_tool_loop(model, system_instruction, user_input):
            calls.append((model, system_instruction, user_input))
            return summary

        monkeypatch.setattr(AG, "_ainvoke_update_llm_with_tool_loop", fake_tool_loop)

        result = run(AG.buildingMarketingBrief({"payload": samplePayload}))

        assert result == {"notes": summary}
        assert calls
        assert "https://example.com/docs" in calls[0][1]
        assert "user-123" in calls[0][1]

    def test_empty_brief_is_rejected(self, samplePayload, monkeypatch):
        async def fake_tool_loop(model, system_instruction, user_input):
            return AgentSummary(marketingBrief="", fileName="brief.txt")

        monkeypatch.setattr(AG, "_ainvoke_update_llm_with_tool_loop", fake_tool_loop)

        with pytest.raises(FailedToBuildMarketingBriefError):
            run(AG.buildingMarketingBrief({"payload": samplePayload}))


class TestGeneratingMarketingPosts:
    def base_state(self, payload):
        return {
            "payload": payload,
            "notes": AgentSummary(marketingBrief="Detailed product context", fileName="m.txt"),
            "posts": [],
            "currentLoopStartNumber": 0,
            "cacheDraft": None,
            "currentFeedback": [],
        }

    def test_cold_path_generates_normalizes_and_caches_draft(
        self, samplePayload, monkeypatch
    ):
        calls = []
        draft = LLMPostGeneration(
            content=LONG_POST.replace(" ", "\\n", 1).replace(",", "\\t", 1),
            publishDate=datetime(2026, 5, 1, 9, 0),
        )

        async def fake_tool_loop(model, system_instruction, user_input):
            calls.append((system_instruction, user_input))
            return draft

        monkeypatch.setattr(AG, "_ainvoke_update_llm_with_tool_loop", fake_tool_loop)

        result = run(AG.generatingMarketingPosts(self.base_state(samplePayload)))

        assert result == {"cacheDraft": draft}
        assert "\n" in draft.content
        assert "\t" in draft.content
        assert "post 1 of 1" in calls[0][1]
        assert "Source URL: https://example.com/docs" in calls[0][1]

    def test_too_short_or_missing_date_response_is_rejected(
        self, samplePayload, monkeypatch
    ):
        async def fake_tool_loop(model, system_instruction, user_input):
            return LLMPostGeneration(content="too short", publishDate=datetime(2026, 5, 1))

        monkeypatch.setattr(AG, "_ainvoke_update_llm_with_tool_loop", fake_tool_loop)

        with pytest.raises(FailedToBuildPosts):
            run(AG.generatingMarketingPosts(self.base_state(samplePayload)))


class TestRegeneratePost:
    def base_state(self, payload):
        return {
            "payload": payload,
            "notes": AgentSummary(marketingBrief="Detailed product context", fileName="m.txt"),
            "posts": [],
            "postToRegenerate": LLMPostGeneration(
                content=LONG_POST,
                publishDate=datetime(2026, 5, 1, 9, 0),
            ),
            "postRegenerationDescription": "make it sharper",
            "cacheDraft": None,
        }

    def test_cold_path_generates_normalizes_and_caches_regenerated_draft(
        self, samplePayload, monkeypatch
    ):
        revised = LLMPostGeneration(
            content=LONG_POST.replace(" ", "\\n", 1),
            publishDate=datetime(2026, 5, 2, 9, 0),
        )

        async def fake_tool_loop(model, system_instruction, user_input):
            assert "make it sharper" in user_input
            assert "user-123" in system_instruction
            return revised

        monkeypatch.setattr(AG, "_ainvoke_update_llm_with_tool_loop", fake_tool_loop)

        result = run(AG.regeneratePost(self.base_state(samplePayload)))

        assert result == {"cacheDraft": revised}
        assert "\n" in revised.content

    def test_invalid_regenerated_response_is_rejected(self, samplePayload, monkeypatch):
        async def fake_tool_loop(model, system_instruction, user_input):
            return LLMPostGeneration(content="short", publishDate=datetime(2026, 5, 2))

        monkeypatch.setattr(AG, "_ainvoke_update_llm_with_tool_loop", fake_tool_loop)

        with pytest.raises(FailedToBuildPosts):
            run(AG.regeneratePost(self.base_state(samplePayload)))
