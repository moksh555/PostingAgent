from fastapi import status #type: ignore

class AuthenticationError(Exception):
    """
    Root exception for this service’s HTTP-facing errors.

    Subclasses carry ``status_code``, ``code``, and ``message`` so a single
    exception handler can return a consistent JSON error body. Use domain
    bases (``LoginError``, ``RegisterError``, ``TokenError``) for catches;
    use this type when you want to handle *any* structured auth error.
    """

    status_code: int = status.HTTP_500_INTERNAL_SERVER_ERROR
    code: str = "internal_error"
    message: str = "An internal error occurred"

    def __init__(self, message: str | None = None, status_code: int | None = None, code: str | None = None) -> None:
        super().__init__(message or self.message)
        if message:
            self.message = message
        if status_code:
            self.status_code = status_code
        if code:
            self.code = code



