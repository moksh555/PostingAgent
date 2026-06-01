import asyncio

import pytest
from fastapi import Response

from app.api.version1 import getUserFromToken as get_user_route
from app.api.version1 import login as login_route
from app.api.version1 import refresh as refresh_route
from app.api.version1 import register as register_route
from app.errorsHandler.loginError import NotAuthorized
from app.errorsHandler.tokenError import CredentialException
from app.models.loginModel import LoginRequest
from app.models.registerModel import RegisterRequest
from app.models.tokenModel import RefreshRequest, Token


class TokenIssuingAuth:
    def __init__(self):
        self.seen_request = None

    async def loginUser(self, request):
        self.seen_request = request
        return (
            Token(accessToken="access-token-value", tokenType="ACCESS_TOKEN"),
            Token(accessToken="refresh-token-value", tokenType="REFRESH_TOKEN"),
        )

    async def registerUser(self, request):
        self.seen_request = request
        return (
            Token(accessToken="access-token-value", tokenType="ACCESS_TOKEN"),
            Token(accessToken="refresh-token-value", tokenType="REFRESH_TOKEN"),
        )


def _set_cookie_headers(response: Response) -> list[str]:
    return [
        value.decode("latin-1")
        for name, value in response.raw_headers
        if name.lower() == b"set-cookie"
    ]


def _assert_session_cookies(response: Response):
    headers = _set_cookie_headers(response)

    assert len(headers) == 2
    refresh_cookie = next(header for header in headers if header.startswith("refresh_token="))
    access_cookie = next(header for header in headers if header.startswith("access_token="))

    assert "refresh_token=refresh-token-value" in refresh_cookie
    assert "HttpOnly" in refresh_cookie
    assert "Secure" in refresh_cookie
    assert "Max-Age=432000" in refresh_cookie

    assert "access_token=access-token-value" in access_cookie
    assert "HttpOnly" in access_cookie
    assert "Secure" in access_cookie
    assert "Max-Age=1800" in access_cookie


def test_login_sets_secure_session_cookies_and_returns_message_only():
    auth = TokenIssuingAuth()
    response = Response()
    request = LoginRequest(email="user@example.com", password="correct-password")

    result = asyncio.run(login_route.login(request, response, auth=auth))

    assert auth.seen_request == request
    assert result.model_dump() == {
        "message": "Login successful",
        "status": "success",
    }
    _assert_session_cookies(response)


def test_register_sets_secure_session_cookies_and_returns_message_only():
    auth = TokenIssuingAuth()
    response = Response()
    request = RegisterRequest(
        email="user@example.com",
        password="CorrectPassword123!",
        dateOfBirth="1990-01-01T00:00:00Z",
        firstName="Test",
        lastName="User",
        phoneNumber="1234567890",
    )

    result = asyncio.run(register_route.register(request, response, auth=auth))

    assert auth.seen_request == request
    assert result.model_dump() == {
        "message": "Register successful",
        "status": "success",
    }
    _assert_session_cookies(response)


def test_refresh_prefers_cookie_token_over_body_token():
    seen_tokens: list[str] = []

    class RefreshAuth:
        def generateAccessTokenFromRefreshToken(self, refresh_token: str):
            seen_tokens.append(refresh_token)
            return Token(accessToken=f"new-{refresh_token}", tokenType="ACCESS_TOKEN")

    result = asyncio.run(
        refresh_route.refresh(
            auth=RefreshAuth(),
            refresh_token_cookie="cookie-refresh-token",
            body=RefreshRequest(refresh_token="body-refresh-token"),
        )
    )

    assert seen_tokens == ["cookie-refresh-token"]
    assert result == Token(
        accessToken="new-cookie-refresh-token",
        tokenType="ACCESS_TOKEN",
    )


def test_refresh_uses_body_token_when_cookie_is_missing():
    seen_tokens: list[str] = []

    class RefreshAuth:
        def generateAccessTokenFromRefreshToken(self, refresh_token: str):
            seen_tokens.append(refresh_token)
            return Token(accessToken=f"new-{refresh_token}", tokenType="ACCESS_TOKEN")

    result = asyncio.run(
        refresh_route.refresh(
            auth=RefreshAuth(),
            refresh_token_cookie=None,
            body=RefreshRequest(refresh_token="body-refresh-token"),
        )
    )

    assert seen_tokens == ["body-refresh-token"]
    assert result.accessToken == "new-body-refresh-token"


def test_refresh_without_cookie_or_body_token_is_rejected():
    class RefreshAuth:
        def generateAccessTokenFromRefreshToken(self, refresh_token: str):
            raise AssertionError("missing refresh token should not call auth service")

    with pytest.raises(CredentialException, match="No Refresh Token provided"):
        asyncio.run(
            refresh_route.refresh(
                auth=RefreshAuth(),
                refresh_token_cookie=None,
                body=None,
            )
        )


def test_get_user_from_token_requires_both_session_cookies(user_model):
    class UserAuth:
        async def getUserFromAccessToken(self, access_token: str, refresh_token: str):
            return user_model

    with pytest.raises(NotAuthorized, match="No Access Token provided"):
        asyncio.run(
            get_user_route.getUserFromToken(
                access_token=None,
                refresh_token="refresh-token",
                auth=UserAuth(),
            )
        )

    with pytest.raises(NotAuthorized, match="No Refresh Token provided"):
        asyncio.run(
            get_user_route.getUserFromToken(
                access_token="access-token",
                refresh_token=None,
                auth=UserAuth(),
            )
        )


def test_get_user_from_token_loads_user_from_session_cookies(user_model):
    seen_tokens: list[tuple[str, str]] = []

    class UserAuth:
        async def getUserFromAccessToken(self, access_token: str, refresh_token: str):
            seen_tokens.append((access_token, refresh_token))
            return user_model

    result = asyncio.run(
        get_user_route.getUserFromToken(
            access_token="access-token",
            refresh_token="refresh-token",
            auth=UserAuth(),
        )
    )

    assert result == user_model
    assert seen_tokens == [("access-token", "refresh-token")]
