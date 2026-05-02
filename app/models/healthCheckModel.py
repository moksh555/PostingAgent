from pydantic import BaseModel, Field  # type:ignore


class HealthCheckModel(BaseModel):
    status: str = Field(..., description="The status of the health check")
    message: str = Field(..., description="The message of the health check")


# the status can be ok, warning, error
# the message can be a short description of the health check
