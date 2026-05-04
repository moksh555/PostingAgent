from pydantic import BaseModel, Field #type: ignore

class LoginRequest(BaseModel):
    email: str = Field(..., description="The email of the user")
    password: str = Field(..., description="The password of the user")

class LoginResponse(BaseModel):
    message: str = Field(..., description="The message of the user")
    status: str = Field(..., description="The status of the user")
