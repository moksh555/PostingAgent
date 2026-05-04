from pydantic import BaseModel, Field #type: ignore

class TokenModel(BaseModel):
    sub: str = Field(..., description="User Id")
    email: str = Field(..., description="User email")

class Token(BaseModel):
    accessToken: str
    tokenType: str


class RefreshRequest(BaseModel):
    """Optional JSON body for `/refresh` when not using the HttpOnly cookie."""

    refresh_token: str | None = None