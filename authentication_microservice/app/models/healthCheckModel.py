from pydantic import BaseModel, Field #type: ignore

class HealthCheckModel(BaseModel):
    status: str = Field(..., description="The status of the health check")
    message: str = Field(..., description="The message of the health check")