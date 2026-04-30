from pydantic import BaseModel, Field  # type:ignore
from datetime import datetime

class UserThreadState(BaseModel):
    threadId: str = Field(..., description="The thread ID")
    status: str = Field(..., description="The status of the thread populated by backend logic")
    startDate: datetime = Field(..., description="The start date of the thread populated by backend DB logic")
    numberOfPosts: int = Field(..., description="The number of posts in the thread populated by backend DB logic")
    campaignURL: str = Field(..., description="The URL of the campaign populated by backend DB logic")
