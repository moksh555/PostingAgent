from pydantic import BaseModel, ConfigDict, Field  # type: ignore
from datetime import datetime


class AgentRunRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

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


class AgentRunResponse(BaseModel):
    status: str = Field(..., description="ok | error")
    message: str = Field(..., description="Human-readable message")
    numberOfPosts: int = Field(..., description="Echo of the requested post count")
    startDate: datetime = Field(..., description="Echo of the requested start date")

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
    content: str 
    publishDate: datetime

class AgentPostGenerationInterrupt(BaseModel):
    actions: str = Field(...,description="The actions to takeon the post chose by user",
    )
    postChangeDescription: str = Field(..., description="The user description of post change if they want to regenerate the post")

class AgentPost(BaseModel):
    content: str
    publishDate: datetime
    platform: str
    postNumber: int
