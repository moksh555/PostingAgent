from pydantic import BaseModel, Field #type: ignore

class TokenModel(BaseModel):
    sub: str = Field(..., description="User Id")

class Token(BaseModel):
    accessToken: str
    tokenType: str