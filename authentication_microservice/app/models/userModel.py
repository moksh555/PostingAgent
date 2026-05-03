from pydantic import BaseModel, Field #type: ignore
from datetime import datetime #type: ignore

class UserModel(BaseModel):
    email: str = Field(..., description="Users email")
    sub: str = Field(..., description="User Id")
    userFirstName: str = Field(..., description="User first name")
    userLastName: str = Field(..., description="User last name")
    phoneNumber: str = Field(..., description="User phone number")
    dateOfBirth: datetime = Field(..., description="User date of birth")
    createdAt: datetime = Field(..., description="User created at")
    isActive: bool = Field(..., description="User is active")
    subscriptionType: str = Field(..., description="User subscription type")

class CreateUserModel(BaseModel):
    email: str = Field(..., description="Users email")
    sub: str = Field(..., description="User Id")
    userFirstName: str = Field(..., description="User first name")
    userLastName: str = Field(..., description="User last name")
    phoneNumber: str = Field(..., description="User phone number")
    dateOfBirth: datetime = Field(..., description="User date of birth")
    createdAt: datetime = Field(..., description="User created at")
    isActive: bool = Field(..., description="User is active")
    passwordHash: str = Field(..., description="User password hash")
    subcriptionType: str = Field(..., description="User subscription type") 

class UserPrivateModel(BaseModel):
    email: str = Field(..., description="Users email")
    sub: str = Field(..., description="User Id")
    userFirstName: str = Field(..., description="User first name")
    userLastName: str = Field(..., description="User last name")
    phoneNumber: str = Field(..., description="User phone number")
    dateOfBirth: datetime = Field(..., description="User date of birth")
    createdAt: datetime = Field(..., description="User created at")
    isActive: bool = Field(..., description="User is active")
    subscriptionType: str = Field(..., description="User subscription type")
    passwordHash: str = Field(..., description="User password hash")