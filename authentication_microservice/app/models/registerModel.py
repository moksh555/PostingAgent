from pydantic import BaseModel, Field #type: ignore
from datetime import datetime #type: ignore

class RegisterRequest(BaseModel):
    email: str = Field(..., description="The email of the user")
    password: str = Field(..., description="The password of the user")
    dateOfBirth: datetime = Field(..., description="The date of birth of the user")
    firstName: str = Field(..., description="The name of the user")
    lastName: str = Field(..., description="The surname of the user")
    phoneNumber: str = Field(..., description="The phone number of the user")

class RegisterResponse(BaseModel):
    message: str = Field(..., description="The message of the user")
    status: str = Field(..., description="The status of the user")