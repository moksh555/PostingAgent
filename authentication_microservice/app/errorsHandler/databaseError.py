from fastapi import status #type: ignore
from app.errorsHandler.baseError import AuthenticationError

class DatabaseError(AuthenticationError):
    """Raised when a database error occurs"""

    status_code = status.HTTP_500_INTERNAL_SERVER_ERROR
    code = "database_error"
    message = "Database error"

    def __init__(self, message: str | None = None, status_code: int | None = None, code: str | None = None) -> None:
        super().__init__(message or self.message, status_code or self.status_code, code or self.code)

class FailedToFetch(DatabaseError):
    """Raised when a database fetch operation fails"""

    status_code = status.HTTP_500_INTERNAL_SERVER_ERROR
    code = "failed_to_fetch"
    message = "Failed to fetch"


class FailedToFetchRow(DatabaseError):
    """Raised when a database fetch row operation fails"""

    status_code = status.HTTP_500_INTERNAL_SERVER_ERROR
    code = "failed_to_fetch_row"
    message = "Failed to fetch row"

class FailedToFetchValue(DatabaseError):
    """Raised when a database fetch value operation fails"""

    status_code = status.HTTP_500_INTERNAL_SERVER_ERROR
    code = "failed_to_fetch_value"
    message = "Failed to fetch value"

class FailedToExecuteStatement(DatabaseError):
    """Raised when a database execute statement operation fails"""

    status_code = status.HTTP_500_INTERNAL_SERVER_ERROR
    code = "failed_to_execute_statement"
    message = "Failed to execute statement"

class FailedToGetUserFromUserId(DatabaseError):
    """Raised when a database get user from user id operation fails"""

    status_code = status.HTTP_500_INTERNAL_SERVER_ERROR
    code = "failed_to_get_user_from_user_id"
    message = "Failed to get user from user id"

class FailedToCreateUser(DatabaseError):
    """Raised when a database create user operation fails"""

    status_code = status.HTTP_500_INTERNAL_SERVER_ERROR
    code = "failed_to_create_user"
    message = "Failed to create user"

class FailedToGetUserFromEmail(DatabaseError):
    """Raised when a database get user from email operation fails"""

    status_code = status.HTTP_500_INTERNAL_SERVER_ERROR
    code = "failed_to_get_user_from_email"
    message = "Failed to get user from email"