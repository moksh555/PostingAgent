from __future__ import annotations

from datetime import datetime
from pydantic import BaseModel, ConfigDict, Field  # type: ignore

class APIResponse(BaseModel):
    status: str = Field(..., description="ok | error")
    state: str = Field(..., description="Human-readable message")
    body: dict | AgentRunResponseCompleted = Field(..., description="The body of the response")

class AgentRunRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    userId: str = Field(..., description="The user ID")
    url: str = Field(
        ...,
        pattern=r"^https?://[^\s/$.?#].[^\s]*$",
        description="The URL to scrape",
    )

    numberOfPosts: int = Field(
        ...,
        gt=0,
        le=9,
        description="The number of posts to generate (1-100)",
    )
    startDate: datetime = Field(
        ...,
        description="The ISO-8601 start date of the campaign",
    )


class AgentRunResponseCompleted(BaseModel):
    status: str = Field(..., description="ok | error")
    state: str = Field(..., description="Human-readable message")
    threadId: str = Field(..., description="The thread ID of the campaign")
    posts: list[AgentPost] = Field(..., description="The posts of the campaign")
    url: str = Field(..., description="The URL of the campaign")
    numberOfPosts: int = Field(..., description="The number of posts of the campaign")
    startDate: datetime = Field(..., description="The start date of the campaign")
    userId: str = Field(..., description="The user ID of the campaign")
    draft: LLMPostGeneration | None = Field(default=None, description="The draft of the post")

    
class AgentSummary(BaseModel):
    marketingBrief: str = Field(
        ...,
        description=(
            "A detailed marketing brief built from the given URL. Write it as a senior product marketing manager would: cover the product/brand, value proposition, target audience, key differentiators, tone of voice, and any relevant context from neighbouring pages. This brief will be used downstream to generate marketing posts there can be multiple posts so the brief should be comprehensive and cover all the relevant information."
        ),
    )
    fileName: str = Field(
        ...,
        description="The file name to save the brief under, ending in '.txt'.",
    )


class LLMPostGeneration(BaseModel):
    content: str = Field(..., description="The full content of the post")
    publishDate: datetime = Field(
        ..., description="The date and time the post will be published"
    )


class AgentPostGenerationInterrupt(BaseModel):
    actions: str = Field(
        ...,
        description="The actions to takeon the post chose by user",
    )
    postChangeDescription: str = Field(
        default="",
        description="The user description of post change if they want to regenerate the post or delte the post for some reason",
    )


class AgentPost(BaseModel):
    content: str = Field(..., description="The content of the post")
    publishDate: datetime = Field(
        ..., description="The date and time the post will be published"
    )
    platform: str = Field(..., description="The platform the post will be published to")
    postNumber: int = Field(default=0, description="The number of the post")
