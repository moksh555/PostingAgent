"""
Token and credential errors.

``TokenError`` is the module base; concrete errors subclass it.
These map to protected routes and JWT / bearer validation, not to the login form.
"""

from app.errorsHandler.baseError import AuthenticationError
from fastapi import status #type: ignore


class TokenError(AuthenticationError):
    """
    Parent type for failures when validating access tokens or bearer credentials.

    Conveys: the caller presented an Authorization header (or similar) that
    could not be accepted—wrong format, bad signature, wrong issuer/algorithm, etc.

    Typical uses: catch-all for JWT pipeline errors before you specialize with
    ``CredentialException``.
    """

    status_code: int = status.HTTP_401_UNAUTHORIZED
    code: str = "token_error"
    message: str = "Token validation error"

    def __init__(self, message: str | None = None, status_code: int | None = None, code: str | None = None) -> None:
        super().__init__(message or self.message, status_code or self.status_code, code or self.code)


class CredentialException(TokenError):
    """
    The bearer token is missing required claims or failed cryptographic checks.

    Conveys: “not authenticated” for API dependencies—expired token, invalid
    signature, malformed JWT, or missing ``sub`` / user id in the payload.
    Clients should obtain a new token (refresh or login again).

    Raise when: ``jwt.decode`` fails, or decoded payload cannot identify a user.
    """

    status_code: int = status.HTTP_401_UNAUTHORIZED
    code: str = "token_error"
    message: str = "Could not validate credentials"
