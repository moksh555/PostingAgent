from fastapi import status #type: ignore
from app.errorsHandler.baseError import AuthenticationError

class NoUserIdError(AuthenticationError):
    """Raised when no user ID is foound in the database"""

    status_code = status.HTTP_400_BAD_REQUEST
    code = "no_user_id"
    message = "User ID is required but was empty"

    def __init__(self, message: str | None = None, status_code: int | None = None, code: str | None = None) -> None:
        super().__init__(message or self.message, status_code or self.status_code, code or self.code)

class NoEmailError(AuthenticationError):
    """Raised when no email is found in the database"""

    status_code = status.HTTP_400_BAD_REQUEST
    code = "no_email"
    message = "Email is required but was empty"

    def __init__(self, message: str | None = None, status_code: int | None = None, code: str | None = None) -> None:
        super().__init__(message or self.message, status_code or self.status_code, code or self.code)