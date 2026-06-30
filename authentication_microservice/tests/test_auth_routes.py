import asyncio
from datetime import UTC, datetime

import pytest
from fastapi import Response  # type: ignore

from app.api.version1.getUserFromToken import getUserFromToken
from app.api.version1.login import login
from app.api.version1.refresh import refresh
from app.api.version1.register import register
from app.errorsHandler.loginError import NotAuthorized
from app.errorsHandler.tokenError import CredentialException
from app.models.loginModel import LoginRequest
from app.models.registerModel import RegisterRequest
from app.models.tokenModel import RefreshRequest, Token


def _set_cookie_headers(response: Response) -> list[str]:
    return [
        value.decode("latin-1")
        for name, value in response.raw_headers
        if name.lower() == b"set-cookie"
    ]


def _assert_secure_http_only_cookie(
    headers: list[str],
    cookie_name: str,
    cookie_value: str,
    max_age: int,
) -> None:
    cookie = next(
        header for header in headers if header.startswith(f"{cookie_name}={cookie_value}")
    )
    assert "HttpOnly" in cookie
    assert "Secure" in cookie
    assert f"Max-Age={max_age}" in cookie


def test_login_sets_secure_http_only_access_and_refresh_cookies():
    class FakeAuth:
        async def loginUser(self, request: LoginRequest):
            return (
                Token(accessToken="access-token", tokenType="ACCESS_TOKEN"),
                Token(accessToken="refresh-token", tokenType="REFRESH_TOKEN"),
            )

    response = Response()

    result = asyncio.run(
        login(
            LoginRequest(email="user@example.com", password="CorrectPass1!"),
            response,
            auth=FakeAuth(),
        )
    )

    assert result.status == "success"
    headers = _set_cookie_headers(response)
    _assert_secure_http_only_cookie(headers, "access_token", "access-token", 1800)
    _assert_secure_http_only_cookie(
        headers,
        "refresh_token",
        "refresh-token",
        3600 * 24 * 5,
    )


def test_register_sets_secure_http_only_access_and_refresh_cookies():
    class FakeAuth:
        async def registerUser(self, request: RegisterRequest):
            return (
                Token(accessToken="new-access-token", tokenType="ACCESS_TOKEN"),
                Token(accessToken="new-refresh-token", tokenType="REFRESH_TOKEN"),
            )

    response = Response()
    request = RegisterRequest(
        email="user@example.com",
        password="CorrectPass1!",
        dateOfBirth=datetime(1990, 1, 1, tzinfo=UTC),
        firstName="Jane",
        lastName="Doe",
        phoneNumber="5551234567",
    )

    result = asyncio.run(register(request, response, auth=FakeAuth()))

    assert result.status == "success"
    headers = _set_cookie_headers(response)
    _assert_secure_http_only_cookie(
        headers,
        "access_token",
        "new-access-token",
        1800,
    )
    _assert_secure_http_only_cookie(
        headers,
        "refresh_token",
        "new-refresh-token",
        3600 * 24 * 5,
    )


def test_refresh_prefers_cookie_token_over_body_token():
    class FakeAuth:
        def __init__(self):
            self.seen_token = None

        def generateAccessTokenFromRefreshToken(self, refresh_token: str) -> Token:
            self.seen_token = refresh_token
            return Token(accessToken=f"access-for-{refresh_token}", tokenType="ACCESS_TOKEN")

    auth = FakeAuth()

    token = asyncio.run(
        refresh(
            auth=auth,
            refresh_token_cookie="cookie-refresh",
            body=RefreshRequest(refresh_token="body-refresh"),
        )
    )

    assert auth.seen_token == "cookie-refresh"
    assert token.accessToken == "access-for-cookie-refresh"


def test_refresh_rejects_missing_refresh_token():
    with pytest.raises(CredentialException, match="No Refresh Token provided"):
        asyncio.run(refresh(auth=object(), refresh_token_cookie=None, body=None))


def test_get_user_from_token_requires_both_cookies(user_model_factory):
    with pytest.raises(NotAuthorized, match="No Access Token provided"):
        asyncio.run(getUserFromToken(access_token=None, refresh_token="refresh"))

    with pytest.raises(NotAuthorized, match="No Refresh Token provided"):
        asyncio.run(getUserFromToken(access_token="access", refresh_token=None))


def test_get_user_from_token_forwards_access_and_refresh_cookies(user_model_factory):
    class FakeAuth:
        def __init__(self):
            self.seen_tokens = None

        async def getUserFromAccessToken(self, access_token: str, refresh_token: str):
            self.seen_tokens = (access_token, refresh_token)
            return user_model_factory(sub="user-123")

    auth = FakeAuth()

    user = asyncio.run(
        getUserFromToken(
            access_token="access-cookie",
            refresh_token="refresh-cookie",
            auth=auth,
        )
    )

    assert auth.seen_tokens == ("access-cookie", "refresh-cookie")
    assert user.sub == "user-123"
