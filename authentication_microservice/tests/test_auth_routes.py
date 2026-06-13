import asyncio
from datetime import datetime, timezone

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


def _set_cookie_headers(response: Response) -> list[str]:
    return [
        value.decode("latin-1")
        for key, value in response.raw_headers
        if key == b"set-cookie"
    ]


def _valid_register_request() -> RegisterRequest:
    return RegisterRequest(
        email="new@example.com",
        password="ValidPass1!",
        dateOfBirth=datetime(1990, 1, 1, tzinfo=timezone.utc),
        firstName="New",
        lastName="User",
        phoneNumber="+15555550123",
    )


class FakeAuth:
    def __init__(self, user_model=None):
        self.user_model = user_model
        self.login_payloads = []
        self.register_payloads = []
        self.refresh_tokens = []
        self.access_refresh_pairs = []

    async def loginUser(self, payload):
        self.login_payloads.append(payload)
        return (
            Token(accessToken="access-token", tokenType="ACCESS_TOKEN"),
            Token(accessToken="refresh-token", tokenType="REFRESH_TOKEN"),
        )

    async def registerUser(self, payload):
        self.register_payloads.append(payload)
        return (
            Token(accessToken="registered-access", tokenType="ACCESS_TOKEN"),
            Token(accessToken="registered-refresh", tokenType="REFRESH_TOKEN"),
        )

    def generateAccessTokenFromRefreshToken(self, refresh_token: str) -> Token:
        self.refresh_tokens.append(refresh_token)
        return Token(accessToken="new-access-token", tokenType="ACCESS_TOKEN")

    async def getUserFromAccessToken(self, access_token: str, refresh_token: str):
        self.access_refresh_pairs.append((access_token, refresh_token))
        return self.user_model


def test_login_sets_http_only_secure_access_and_refresh_cookies():
    response = Response()
    auth = FakeAuth()
    payload = LoginRequest(email="Person@Example.com", password="ValidPass1!")

    result = asyncio.run(login(payload, response, auth))

    assert result.message == "Login successful"
    assert auth.login_payloads == [payload]
    cookies = _set_cookie_headers(response)
    assert any(
        "refresh_token=refresh-token" in cookie
        and "HttpOnly" in cookie
        and "Secure" in cookie
        and "Max-Age=432000" in cookie
        for cookie in cookies
    )
    assert any(
        "access_token=access-token" in cookie
        and "HttpOnly" in cookie
        and "Secure" in cookie
        and "Max-Age=1800" in cookie
        for cookie in cookies
    )


def test_register_sets_cookies_from_issued_tokens():
    response = Response()
    auth = FakeAuth()
    payload = _valid_register_request()

    result = asyncio.run(register(payload, response, auth))

    assert result.message == "Register successful"
    assert auth.register_payloads == [payload]
    cookies = _set_cookie_headers(response)
    assert any("refresh_token=registered-refresh" in cookie for cookie in cookies)
    assert any("access_token=registered-access" in cookie for cookie in cookies)


def test_refresh_prefers_cookie_token_over_request_body():
    auth = FakeAuth()

    result = asyncio.run(
        refresh(
            auth=auth,
            refresh_token_cookie="cookie-refresh",
            body=RefreshRequest(refresh_token="body-refresh"),
        ),
    )

    assert result == Token(accessToken="new-access-token", tokenType="ACCESS_TOKEN")
    assert auth.refresh_tokens == ["cookie-refresh"]


def test_refresh_rejects_missing_cookie_and_body_token():
    with pytest.raises(CredentialException, match="No Refresh Token provided"):
        asyncio.run(refresh(auth=FakeAuth(), refresh_token_cookie=None, body=None))


def test_get_user_from_token_requires_both_cookies(user_model):
    auth = FakeAuth(user_model=user_model)

    with pytest.raises(NotAuthorized, match="No Access Token provided"):
        asyncio.run(
            getUserFromToken(
                access_token=None,
                refresh_token="refresh-token",
                auth=auth,
            ),
        )

    with pytest.raises(NotAuthorized, match="No Refresh Token provided"):
        asyncio.run(
            getUserFromToken(
                access_token="access-token",
                refresh_token=None,
                auth=auth,
            ),
        )

    assert auth.access_refresh_pairs == []


def test_get_user_from_token_passes_cookie_pair_to_auth_service(user_model):
    auth = FakeAuth(user_model=user_model)

    result = asyncio.run(
        getUserFromToken(
            access_token="access-token",
            refresh_token="refresh-token",
            auth=auth,
        ),
    )

    assert result == user_model
    assert auth.access_refresh_pairs == [("access-token", "refresh-token")]
