"""
Register domain errors.

``RegisterError`` is the module base; concrete errors subclass it.
Catch ``RegisterError`` for all sign-up failures; use subclasses for specific reasons.
"""

from app.errorsHandler.baseError import AuthenticationError
from fastapi import status #type: ignore


class RegisterError(AuthenticationError):
    """
    Parent type for anything that went wrong while processing registration.

    Conveys: the failure is scoped to account creation (validation rules, conflicts,
    policy), not to login or JWT verification.

    Typical uses: email already taken, weak password policy, server-side validation
    after the body parsed successfully.
    """

    status_code: int = status.HTTP_400_BAD_REQUEST
    code: str = "register_error"
    message: str = "Register error"

    def __init__(self, message: str | None = None, status_code: int | None = None, code: str | None = None) -> None:
        super().__init__(message or self.message, status_code or self.status_code, code or self.code)


class RegisterPayloadError(RegisterError):
    """
    The register request body is structurally or semantically invalid.

    Conveys: same idea as FastAPI/Pydantic 422—fields wrong type, missing required
    fields, or business rules on the *shape* of the payload (not “email taken”).

    Raise when: manual checks fail on ``RegisterRequest`` beyond what Pydantic
    already validates, or when you re-map validation into this type for a uniform
    ``register_error`` / ``payload_error`` response.
    """

    status_code: int = status.HTTP_422_UNPROCESSABLE_ENTITY
    code: str = "payload_error"
    message: str = "Invalid request payload"
