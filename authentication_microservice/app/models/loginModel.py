from pydantic import BaseModel, Field #type: ignore

class LoginRequest(BaseModel):
    email: str = Field(..., description="The email of the user")
    password: str = Field(..., description="The password of the user")

class LoginResponse(BaseModel):
    access_token: str = Field(..., description="The access token of the user")
    refresh_token: str = Field(..., description="The refresh token of the user")