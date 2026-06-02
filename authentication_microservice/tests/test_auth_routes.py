import asyncio
from datetime import UTC, datetime

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


class FakeAuthService:
    def __init__(self):
        self.refresh_tokens: list[str] = []
        self.user_tokens: list[tuple[str, str]] = []

    def generateAccessTokenFromRefreshToken(self, refresh_token: str) -> Token:
        self.refresh_tokens.append(refresh_token)
        return Token(accessToken="new-access-token", tokenType="ACCESS_TOKEN")

    async def getUserFromAccessToken(self, access_token: str, refresh_token: str):
        self.user_tokens.append((access_token, refresh_token))
        return {"sub": "user-123"}

    async def loginUser(self, request: LoginRequest):
        return (
            Token(accessToken="login-access-token", tokenType="ACCESS_TOKEN"),
            Token(accessToken="login-refresh-token", tokenType="REFRESH_TOKEN"),
        )

    async def registerUser(self, request: RegisterRequest):
        return (
            Token(accessToken="register-access-token", tokenType="ACCESS_TOKEN"),
            Token(accessToken="register-refresh-token", tokenType="REFRESH_TOKEN"),
        )


def set_cookie_headers(response: Response) -> list[str]:
    return [
        value.decode()
        for key, value in response.raw_headers
        if key.lower() == b"set-cookie"
    ]


def test_refresh_uses_cookie_before_body_token():
    auth = FakeAuthService()

    token = asyncio.run(
        refresh(
            auth=auth,
            refresh_token_cookie="cookie-refresh-token",
            body=RefreshRequest(refresh_token="body-refresh-token"),
        )
    )

    assert token == Token(accessToken="new-access-token", tokenType="ACCESS_TOKEN")
    assert auth.refresh_tokens == ["cookie-refresh-token"]


def test_refresh_requires_cookie_or_body_token():
    with pytest.raises(CredentialException, match="No Refresh Token provided"):
        asyncio.run(refresh(auth=FakeAuthService(), refresh_token_cookie=None, body=None))


def test_get_user_from_token_requires_both_cookies():
    auth = FakeAuthService()

    with pytest.raises(NotAuthorized, match="No Access Token provided"):
        asyncio.run(
            getUserFromToken(
                access_token=None,
                refresh_token="refresh-token",
                auth=auth,
            )
        )
    with pytest.raises(NotAuthorized, match="No Refresh Token provided"):
        asyncio.run(
            getUserFromToken(
                access_token="access-token",
                refresh_token=None,
                auth=auth,
            )
        )
    assert auth.user_tokens == []


def test_get_user_from_token_passes_cookie_pair_to_service():
    auth = FakeAuthService()

    result = asyncio.run(
        getUserFromToken(
            access_token="access-token",
            refresh_token="refresh-token",
            auth=auth,
        )
    )

    assert result == {"sub": "user-123"}
    assert auth.user_tokens == [("access-token", "refresh-token")]


@pytest.mark.parametrize(
    ("route_func", "request_obj", "access_value", "refresh_value", "message"),
    [
        (
            login,
            LoginRequest(email="user@example.com", password="Password1!"),
            "login-access-token",
            "login-refresh-token",
            "Login successful",
        ),
        (
            register,
            RegisterRequest(
                email="user@example.com",
                password="Password1!",
                dateOfBirth=datetime(1990, 1, 1, tzinfo=UTC),
                firstName="Ada",
                lastName="Lovelace",
                phoneNumber="+15555550123",
            ),
            "register-access-token",
            "register-refresh-token",
            "Register successful",
        ),
    ],
)
def test_login_and_register_set_secure_http_only_session_cookies(
    route_func,
    request_obj,
    access_value,
    refresh_value,
    message,
):
    response = Response()

    result = asyncio.run(route_func(request_obj, response, auth=FakeAuthService()))

    assert result.message == message
    assert result.status == "success"
    cookie_headers = set_cookie_headers(response)
    assert len(cookie_headers) == 2
    assert any(
        header.startswith(f"refresh_token={refresh_value};")
        and "HttpOnly" in header
        and "Secure" in header
        and "Max-Age=432000" in header
        for header in cookie_headers
    )
    assert any(
        header.startswith(f"access_token={access_value};")
        and "HttpOnly" in header
        and "Secure" in header
        and "Max-Age=1800" in header
        for header in cookie_headers
    )
