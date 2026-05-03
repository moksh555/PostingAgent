"""
Login domain errors.

``LoginError`` is the module base; concrete errors subclass it.
Catch ``LoginError`` to handle the whole login flow; catch subclasses for specific cases.
"""

from app.errorsHandler.baseError import AuthenticationError
from fastapi import status #type: ignore


class LoginError(AuthenticationError):
    """
    Parent type for anything that went wrong while processing a login request.

    Conveys: the failure is scoped to sign-in (not registration or token refresh).

    Typical uses: wrapping unexpected errors from the login service, or generic
    “login failed” when you do not want to reveal whether the email exists.
    """

    status_code: int = status.HTTP_400_BAD_REQUEST
    code: str = "login_error"
    message: str = "Login error"

    def __init__(self, message: str | None = None, status_code: int | None = None, code: str | None = None) -> None:
        super().__init__(message or self.message, status_code or self.status_code, code or self.code)


class NoEmailorPasswordFound(LoginError):
    """
    The client did not supply credentials the endpoint requires.

    Conveys: missing or empty email and/or password in the payload—user error,
    not “wrong password.” Distinct from ``NotAuthorized`` (bad credentials
    after lookup).

    Raise when: validation fails before you hit the database (e.g. blank fields).
    """

    status_code: int = status.HTTP_401_UNAUTHORIZED
    code: str = "login_error"
    message: str = "Unauthorized Access No Email Found"


class NotAuthorized(LoginError):
    """
    Credentials were present but do not allow access.

    Conveys: email/password mismatch, inactive account, or any “we know who
    you claim to be but we won’t let you in” outcome. Do not use for malformed
    bodies (use validation / ``NoEmailorPasswordFound`` / 422 as appropriate).

    Raise when: DB lookup succeeds but password/hash check fails, or policy denies login.
    """

    status_code: int = status.HTTP_401_UNAUTHORIZED
    code: str = "login_error"
    message: str = "Unauthorized Access: Email and Password do not match"
