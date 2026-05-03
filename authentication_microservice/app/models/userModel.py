from pydantic import BaseModel, Field #type: ignore

class UserModel(BaseModel):
    email: str = Field(..., description="Users email")
    sub: str = Field(..., description="User Id")
    userFirstName: str = Field(..., description="User first name")
    userLastName: str = Field(..., description="User last name")
    
