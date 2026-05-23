"""Focused regression tests for the async agent graph helpers and nodes."""

import asyncio
from datetime import datetime
from types import SimpleNamespace

import pytest
from langchain_core.messages import AIMessage, HumanMessage, SystemMessage, ToolMessage  # type: ignore

from app.errorsHandler.errors import (
    FailedToBuildContext,
    FailedToBuildMarketingBriefError,
    FailedToBuildPosts,
)
from app.models.AgentModels import AgentSummary, LLMPostGeneration
from app.services import agentGraph as AG


LONG_POST = (
    "This launch announcement highlights concrete customer value, clear proof "
    "points, and an actionable next step for teams evaluating the product today."
)


def run_async(coro):
    return asyncio.run(coro)


class AsyncTool:
    def __init__(self, result: str):
        self.result = result
        self.calls: list[dict] = []

    async def ainvoke(self, args):
        self.calls.append(args)
        return self.result


class QueuedAsyncModel:
    def __init__(self, responses):
        self.responses = list(responses)
        self.calls: list[list] = []

    async def ainvoke(self, messages):
        self.calls.append(list(messages))
        if not self.responses:
            raise AssertionError("QueuedAsyncModel exhausted")
        value = self.responses.pop(0)
        if isinstance(value, BaseException):
            raise value
        return value


class FakeS3:
    def __init__(self, existing_keys=frozenset(), fail_on_check=False):
        self.existing_keys = set(existing_keys)
        self.fail_on_check = fail_on_check
        self.checked: list[str] = []
        self.puts: list[dict] = []

    async def check_if_file_exists(self, *, bucketName, key):
        if self.fail_on_check:
            raise RuntimeError("s3 unavailable")
        self.checked.append(key)
        return key in self.existing_keys

    async def put_object(self, *, body, bucketName, key):
        self.puts.append({"body": body, "bucketName": bucketName, "key": key})


class TestParseToolCall:
    def test_dict_shape_preserves_name_args_and_id(self):
        assert AG._parse_tool_call(
            {"name": "write_file_to_S3", "args": {"key": "k"}, "id": "call-1"}
        ) == ("write_file_to_S3", {"key": "k"}, "call-1")

    def test_object_shape_defaults_non_dict_args_to_empty_dict(self):
        call = SimpleNamespace(name="check_if_file_exists_S3", args="bad", id=None)

        assert AG._parse_tool_call(call) == ("check_if_file_exists_S3", {}, "")

    def test_unknown_shape_raises_type_error(self):
        with pytest.raises(TypeError, match="Unrecognized tool_call shape"):
            AG._parse_tool_call(SimpleNamespace(args={}))


class TestToolLoop:
    def test_executes_requested_tool_and_returns_final_message(self, monkeypatch):
        read_tool = AsyncTool("existing summary")
        monkeypatch.setattr(AG, "get_file_content_S3", read_tool)
        monkeypatch.setattr(AG, "check_if_file_exists_S3", AsyncTool("true"))
        monkeypatch.setattr(AG, "write_file_to_S3", AsyncTool("ok"))
        final = AIMessage(content="done")
        model = QueuedAsyncModel(
            [
                AIMessage(
                    content="",
                    tool_calls=[
                        {
                            "name": "get_file_content_S3",
                            "args": {"file_path": "UserNotes/u/knowledge/previous.txt"},
                            "id": "call-1",
                        }
                    ],
                ),
                final,
            ]
        )

        result = run_async(
            AG._ainvoke_update_llm_with_tool_loop(
                model,
                "system",
                "user",
            )
        )

        assert result is final
        assert read_tool.calls == [{"file_path": "UserNotes/u/knowledge/previous.txt"}]
        second_call_messages = model.calls[1]
        assert isinstance(second_call_messages[0], SystemMessage)
        assert isinstance(second_call_messages[1], HumanMessage)
        assert isinstance(second_call_messages[-1], ToolMessage)
        assert second_call_messages[-1].content == "existing summary"
        assert second_call_messages[-1].tool_call_id == "call-1"

    def test_unknown_tool_request_raises_value_error(self):
        model = QueuedAsyncModel(
            [
                AIMessage(
                    content="",
                    tool_calls=[
                        {"name": "delete_everything", "args": {}, "id": "call-1"}
                    ],
                )
            ]
        )

        with pytest.raises(ValueError, match="Unknown tool requested"):
            run_async(AG._ainvoke_update_llm_with_tool_loop(model, "system", "user"))

    def test_raises_when_model_never_finishes_tool_rounds(self, monkeypatch):
        monkeypatch.setattr(AG, "check_if_file_exists_S3", AsyncTool("false"))
        model = QueuedAsyncModel(
            [
                AIMessage(
                    content="",
                    tool_calls=[
                        {"name": "check_if_file_exists_S3", "args": {}, "id": "call-1"}
                    ],
                ),
                AIMessage(
                    content="",
                    tool_calls=[
                        {"name": "check_if_file_exists_S3", "args": {}, "id": "call-2"}
                    ],
                ),
            ]
        )

        with pytest.raises(ValueError, match="did not finish after 2 tool rounds"):
            run_async(
                AG._ainvoke_update_llm_with_tool_loop(
                    model, "system", "user", max_tool_rounds=2
                )
            )


class TestBuildingContext:
    def test_creates_missing_user_knowledge_files(self, samplePayload, monkeypatch):
        s3 = FakeS3()
        monkeypatch.setattr(AG, "get_s3_connection", lambda: s3)

        assert run_async(AG.buildingContext({"payload": samplePayload})) == {}

        assert s3.checked == [
            "UserNotes/user-123/knowledge/previous_summary.txt",
            "UserNotes/user-123/knowledge/feedback_summary.txt",
        ]
        assert s3.puts == [
            {
                "body": "",
                "bucketName": "test-bucket",
                "key": "UserNotes/user-123/knowledge/previous_summary.txt",
            },
            {
                "body": "",
                "bucketName": "test-bucket",
                "key": "UserNotes/user-123/knowledge/feedback_summary.txt",
            },
        ]

    def test_leaves_existing_knowledge_files_untouched(
        self, samplePayload, monkeypatch
    ):
        s3 = FakeS3(
            existing_keys={
                "UserNotes/user-123/knowledge/previous_summary.txt",
                "UserNotes/user-123/knowledge/feedback_summary.txt",
            }
        )
        monkeypatch.setattr(AG, "get_s3_connection", lambda: s3)

        assert run_async(AG.buildingContext({"payload": samplePayload})) == {}

        assert s3.puts == []

    def test_wraps_s3_errors(self, samplePayload, monkeypatch):
        monkeypatch.setattr(AG, "get_s3_connection", lambda: FakeS3(fail_on_check=True))

        with pytest.raises(FailedToBuildContext, match="s3 unavailable"):
            run_async(AG.buildingContext({"payload": samplePayload}))


class TestBuildingMarketingBrief:
    def test_happy_path_returns_notes(self, samplePayload, monkeypatch):
        summary = AgentSummary(marketingBrief="A real brief.", fileName="brief.txt")

        async def fake_tool_loop(model, system_instruction, user_input):
            assert model is AG.strcturedSummaryWithTool
            assert samplePayload.userId in system_instruction
            assert samplePayload.url in system_instruction
            assert "Generate a marketing brief" in user_input
            return summary

        monkeypatch.setattr(AG, "_ainvoke_update_llm_with_tool_loop", fake_tool_loop)

        assert run_async(AG.buildingMarketingBrief({"payload": samplePayload})) == {
            "notes": summary
        }

    def test_empty_file_name_raises(self, samplePayload, monkeypatch):
        async def fake_tool_loop(*args, **kwargs):
            return AgentSummary(marketingBrief="brief", fileName="")

        monkeypatch.setattr(AG, "_ainvoke_update_llm_with_tool_loop", fake_tool_loop)

        with pytest.raises(FailedToBuildMarketingBriefError, match="invalid"):
            run_async(AG.buildingMarketingBrief({"payload": samplePayload}))


class TestGeneratingMarketingPostsProduce:
    def _base_state(self, payload):
        return {
            "payload": payload,
            "notes": AgentSummary(marketingBrief="notes", fileName="brief.txt"),
            "posts": [],
            "currentLoopStartNumber": 0,
            "cacheDraft": None,
            "currentFeedback": [],
        }

    def test_produces_valid_draft_without_appending_posts(
        self, samplePayload, monkeypatch
    ):
        draft = LLMPostGeneration(
            content=LONG_POST,
            publishDate=datetime(2026, 5, 1, 9, 0),
        )

        async def fake_tool_loop(model, system_instruction, user_input):
            assert model is AG.structuredPostGenerationLLMWithTool
            assert "Generate exactly ONE post for slot 1" in user_input
            return draft

        monkeypatch.setattr(AG, "_ainvoke_update_llm_with_tool_loop", fake_tool_loop)

        result = run_async(AG.generatingMarketingPosts(self._base_state(samplePayload)))

        assert result == {"cacheDraft": draft}
        assert "posts" not in result

    def test_short_content_raises_failed_to_build_posts(
        self, samplePayload, monkeypatch
    ):
        async def fake_tool_loop(*args, **kwargs):
            return LLMPostGeneration(
                content="too short", publishDate=datetime(2026, 5, 1, 9, 0)
            )

        monkeypatch.setattr(AG, "_ainvoke_update_llm_with_tool_loop", fake_tool_loop)

        with pytest.raises(FailedToBuildPosts, match="too-short"):
            run_async(AG.generatingMarketingPosts(self._base_state(samplePayload)))


class TestRoutingGeneratePostsNode:
    def test_regenerate_truthy_routes_to_regen(self, samplePayload):
        assert (
            AG.routingGneratePostsNode(
                {
                    "regeneratePost": True,
                    "payload": samplePayload,
                    "currentLoopStartNumber": 0,
                }
            )
            == "Regenerating_With_Feedback"
        )

    def test_more_slots_remaining_routes_back_to_generation(self, multiPostPayload):
        assert (
            AG.routingGneratePostsNode(
                {
                    "regeneratePost": False,
                    "payload": multiPostPayload,
                    "currentLoopStartNumber": 1,
                }
            )
            == "Drafting_And_Reviewing_Posts"
        )

    def test_all_slots_done_routes_to_persistence(self, samplePayload):
        assert (
            AG.routingGneratePostsNode(
                {
                    "regeneratePost": False,
                    "payload": samplePayload,
                    "currentLoopStartNumber": 1,
                }
            )
            == "Saving_Data_To_Database"
        )


class TestAggregateSummary:
    def test_aggregates_only_when_both_summary_updates_succeed(self):
        assert run_async(
            AG.aggregateSummary(
                {
                    "updatedCurrentFeedback": True,
                    "updatedPreviousSummary": True,
                }
            )
        ) == {"aggregatedSummary": True}
        assert run_async(
            AG.aggregateSummary(
                {
                    "updatedCurrentFeedback": True,
                    "updatedPreviousSummary": False,
                }
            )
        ) == {"aggregatedSummary": False}
