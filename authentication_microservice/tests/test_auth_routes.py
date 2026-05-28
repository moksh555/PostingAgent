import asyncio

import pytest
from fastapi import Response

from app.api.version1.getUserFromToken import getUserFromToken
from app.api.version1.login import login
from app.api.version1.refresh import refresh
from app.api.version1.register import register
from app.errorsHandler.loginError import NotAuthorized
from app.errorsHandler.tokenError import CredentialException
from app.models.loginModel import LoginRequest
from app.models.registerModel import RegisterRequest
from app.models.tokenModel import RefreshRequest, Token


class FakeAuth:
    def __init__(self):
        self.refresh_calls = []
        self.user_from_token_calls = []
        self.login_calls = []
        self.register_calls = []

    def generateAccessTokenFromRefreshToken(self, refresh_token: str) -> Token:
        self.refresh_calls.append(refresh_token)
        return Token(accessToken=f"access-for-{refresh_token}", tokenType="ACCESS_TOKEN")

    async def getUserFromAccessToken(self, access_token: str, refresh_token: str):
        self.user_from_token_calls.append((access_token, refresh_token))
        return {"sub": "user-123"}

    async def loginUser(self, request: LoginRequest):
        self.login_calls.append(request)
        return (
            Token(accessToken="access-token-value", tokenType="ACCESS_TOKEN"),
            Token(accessToken="refresh-token-value", tokenType="REFRESH_TOKEN"),
        )

    async def registerUser(self, request: RegisterRequest):
        self.register_calls.append(request)
        return (
            Token(accessToken="access-token-value", tokenType="ACCESS_TOKEN"),
            Token(accessToken="refresh-token-value", tokenType="REFRESH_TOKEN"),
        )


def _set_cookie_headers(response: Response) -> list[str]:
    return [
        value.decode("latin-1")
        for key, value in response.raw_headers
        if key.decode("latin-1").lower() == "set-cookie"
    ]


def test_refresh_prefers_http_only_cookie_over_body_token():
    auth = FakeAuth()

    token = asyncio.run(
        refresh(
            auth=auth,
            refresh_token_cookie="cookie-token",
            body=RefreshRequest(refresh_token="body-token"),
        ),
    )

    assert token == Token(accessToken="access-for-cookie-token", tokenType="ACCESS_TOKEN")
    assert auth.refresh_calls == ["cookie-token"]


def test_refresh_accepts_body_token_when_cookie_missing():
    auth = FakeAuth()

    token = asyncio.run(
        refresh(
            auth=auth,
            refresh_token_cookie=None,
            body=RefreshRequest(refresh_token="body-token"),
        ),
    )

    assert token == Token(accessToken="access-for-body-token", tokenType="ACCESS_TOKEN")
    assert auth.refresh_calls == ["body-token"]


def test_refresh_requires_a_refresh_token():
    with pytest.raises(CredentialException, match="No Refresh Token provided"):
        asyncio.run(refresh(auth=FakeAuth(), refresh_token_cookie=None, body=None))


def test_get_user_from_token_requires_access_cookie_before_auth_call():
    auth = FakeAuth()

    with pytest.raises(NotAuthorized, match="No Access Token provided"):
        asyncio.run(
            getUserFromToken(
                access_token=None,
                refresh_token="refresh-token",
                auth=auth,
            ),
        )

    assert auth.user_from_token_calls == []


def test_get_user_from_token_requires_refresh_cookie_before_auth_call():
    auth = FakeAuth()

    with pytest.raises(NotAuthorized, match="No Refresh Token provided"):
        asyncio.run(
            getUserFromToken(
                access_token="access-token",
                refresh_token=None,
                auth=auth,
            ),
        )

    assert auth.user_from_token_calls == []


def test_get_user_from_token_passes_cookie_tokens_to_auth_service():
    auth = FakeAuth()

    user = asyncio.run(
        getUserFromToken(
            access_token="access-token",
            refresh_token="refresh-token",
            auth=auth,
        ),
    )

    assert user == {"sub": "user-123"}
    assert auth.user_from_token_calls == [("access-token", "refresh-token")]


def test_login_sets_secure_http_only_access_and_refresh_cookies():
    response = Response()

    result = asyncio.run(
        login(
            request=LoginRequest(email="user@example.com", password="Password1!"),
            response=response,
            auth=FakeAuth(),
        ),
    )

    cookies = _set_cookie_headers(response)
    assert result.message == "Login successful"
    assert result.status == "success"
    assert any(
        "refresh_token=refresh-token-value" in cookie
        and "Max-Age=432000" in cookie
        and "HttpOnly" in cookie
        and "Secure" in cookie
        for cookie in cookies
    )
    assert any(
        "access_token=access-token-value" in cookie
        and "Max-Age=1800" in cookie
        and "HttpOnly" in cookie
        and "Secure" in cookie
        for cookie in cookies
    )


def test_register_sets_secure_http_only_access_and_refresh_cookies():
    response = Response()

    result = asyncio.run(
        register(
            request=RegisterRequest(
                email="user@example.com",
                password="Password1!",
                dateOfBirth="2000-01-01T00:00:00Z",
                firstName="Test",
                lastName="User",
                phoneNumber="+15555550123",
            ),
            response=response,
            auth=FakeAuth(),
        ),
    )

    cookies = _set_cookie_headers(response)
    assert result.message == "Register successful"
    assert result.status == "success"
    assert any(
        "refresh_token=refresh-token-value" in cookie
        and "Max-Age=432000" in cookie
        and "HttpOnly" in cookie
        and "Secure" in cookie
        for cookie in cookies
    )
    assert any(
        "access_token=access-token-value" in cookie
        and "Max-Age=1800" in cookie
        and "HttpOnly" in cookie
        and "Secure" in cookie
        for cookie in cookies
    )
