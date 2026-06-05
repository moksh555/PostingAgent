import asyncio
from datetime import datetime, timezone

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


def _run(coro):
    return asyncio.run(coro)


def _cookie_headers(response: Response) -> list[str]:
    return [
        value.decode("latin-1")
        for key, value in response.raw_headers
        if key == b"set-cookie"
    ]


def _assert_session_cookies(response: Response) -> None:
    cookies = _cookie_headers(response)
    assert any(
        "refresh_token=refresh-value" in cookie
        and "Max-Age=432000" in cookie
        and "HttpOnly" in cookie
        and "Secure" in cookie
        for cookie in cookies
    )
    assert any(
        "access_token=access-value" in cookie
        and "Max-Age=1800" in cookie
        and "HttpOnly" in cookie
        and "Secure" in cookie
        for cookie in cookies
    )


class FakeSessionAuth:
    async def loginUser(self, payload):
        return (
            Token(accessToken="access-value", tokenType="ACCESS_TOKEN"),
            Token(accessToken="refresh-value", tokenType="REFRESH_TOKEN"),
        )

    async def registerUser(self, payload):
        return (
            Token(accessToken="access-value", tokenType="ACCESS_TOKEN"),
            Token(accessToken="refresh-value", tokenType="REFRESH_TOKEN"),
        )


def test_login_sets_http_only_session_cookies():
    response = Response()
    payload = LoginRequest(email="user@example.com", password="Secret123!")

    result = _run(login_route.login(payload, response, FakeSessionAuth()))

    assert result.message == "Login successful"
    assert result.status == "success"
    _assert_session_cookies(response)


def test_register_sets_http_only_session_cookies():
    response = Response()
    payload = RegisterRequest(
        email="user@example.com",
        password="Secret123!",
        dateOfBirth=datetime(1990, 1, 1, tzinfo=timezone.utc),
        firstName="Ada",
        lastName="Lovelace",
        phoneNumber="+15555550123",
    )

    result = _run(register_route.register(payload, response, FakeSessionAuth()))

    assert result.message == "Register successful"
    assert result.status == "success"
    _assert_session_cookies(response)


class FakeRefreshAuth:
    def __init__(self):
        self.refresh_tokens: list[str] = []

    def generateAccessTokenFromRefreshToken(self, refresh_token: str) -> Token:
        self.refresh_tokens.append(refresh_token)
        return Token(accessToken=f"new-{refresh_token}", tokenType="ACCESS_TOKEN")


def test_refresh_prefers_http_only_cookie_over_request_body():
    auth = FakeRefreshAuth()

    result = _run(
        refresh_route.refresh(
            auth=auth,
            refresh_token_cookie="cookie-token",
            body=RefreshRequest(refresh_token="body-token"),
        )
    )

    assert result.accessToken == "new-cookie-token"
    assert result.tokenType == "ACCESS_TOKEN"
    assert auth.refresh_tokens == ["cookie-token"]


def test_refresh_requires_cookie_or_body_token():
    with pytest.raises(CredentialException, match="No Refresh Token provided"):
        _run(refresh_route.refresh(auth=FakeRefreshAuth(), refresh_token_cookie=None, body=None))


class FakeGetUserAuth:
    def __init__(self, user):
        self.user = user
        self.tokens: list[tuple[str, str]] = []

    async def getUserFromAccessToken(self, access_token: str, refresh_token: str):
        self.tokens.append((access_token, refresh_token))
        return self.user


@pytest.mark.parametrize(
    ("access_token", "refresh_token", "message"),
    [
        (None, "refresh-token", "No Access Token provided"),
        ("access-token", None, "No Refresh Token provided"),
    ],
)
def test_get_user_from_token_requires_both_auth_cookies(
    access_token,
    refresh_token,
    message,
    sample_user,
):
    with pytest.raises(NotAuthorized, match=message):
        _run(
            get_user_route.getUserFromToken(
                access_token=access_token,
                refresh_token=refresh_token,
                auth=FakeGetUserAuth(sample_user),
            )
        )


def test_get_user_from_token_passes_cookie_tokens_to_service(sample_user):
    auth = FakeGetUserAuth(sample_user)

    user = _run(
        get_user_route.getUserFromToken(
            access_token="access-token",
            refresh_token="refresh-token",
            auth=auth,
        )
    )

    assert user == sample_user
    assert auth.tokens == [("access-token", "refresh-token")]
