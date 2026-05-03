from pydantic import BaseModel, Field #type: ignore

class TokenModel(BaseModel):
    sub: str = Field(..., description="User Id")
    email: str = Field(..., description="User email")

class Token(BaseModel):
    accessToken: str
    tokenType: str