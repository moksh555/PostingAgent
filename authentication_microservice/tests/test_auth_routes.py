import asyncio
from datetime import datetime, timezone
from typing import Iterable

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


class FakeRefreshAuth:
    def __init__(self):
        self.refresh_tokens: list[str] = []

    def generateAccessTokenFromRefreshToken(self, refresh_token: str) -> Token:
        self.refresh_tokens.append(refresh_token)
        return Token(accessToken=f"access-for-{refresh_token}", tokenType="ACCESS_TOKEN")


class FakeSessionAuth:
    def __init__(self, sample_user):
        self.sample_user = sample_user
        self.access_refresh_pairs: list[tuple[str, str]] = []

    async def getUserFromAccessToken(self, access_token: str, refresh_token: str):
        self.access_refresh_pairs.append((access_token, refresh_token))
        return self.sample_user


class FakeCookieIssuingAuth:
    def __init__(self, method_name: str):
        self.method_name = method_name
        self.payloads = []

    async def loginUser(self, payload):
        self.payloads.append(payload)
        return self._tokens()

    async def registerUser(self, payload):
        self.payloads.append(payload)
        return self._tokens()

    def _tokens(self):
        return (
            Token(accessToken="access-token", tokenType="ACCESS_TOKEN"),
            Token(accessToken="refresh-token", tokenType="REFRESH_TOKEN"),
        )


def _set_cookie_headers(response: Response) -> list[str]:
    return [
        value.decode()
        for key, value in response.raw_headers
        if key.lower() == b"set-cookie"
    ]


def _assert_auth_cookies(headers: Iterable[str]) -> None:
    headers = list(headers)
    assert any("refresh_token=refresh-token" in header for header in headers)
    assert any("access_token=access-token" in header for header in headers)
    assert all("HttpOnly" in header for header in headers)
    assert all("Secure" in header for header in headers)


def test_refresh_prefers_cookie_token_over_body_token():
    auth = FakeRefreshAuth()

    result = asyncio.run(
        refresh(
            auth=auth,
            refresh_token_cookie="cookie-refresh",
            body=RefreshRequest(refresh_token="body-refresh"),
        ),
    )

    assert result == Token(
        accessToken="access-for-cookie-refresh",
        tokenType="ACCESS_TOKEN",
    )
    assert auth.refresh_tokens == ["cookie-refresh"]


def test_refresh_falls_back_to_body_token_when_cookie_missing():
    auth = FakeRefreshAuth()

    result = asyncio.run(
        refresh(
            auth=auth,
            refresh_token_cookie=None,
            body=RefreshRequest(refresh_token="body-refresh"),
        ),
    )

    assert result.accessToken == "access-for-body-refresh"
    assert auth.refresh_tokens == ["body-refresh"]


def test_refresh_requires_a_refresh_token():
    auth = FakeRefreshAuth()

    with pytest.raises(CredentialException, match="No Refresh Token provided"):
        asyncio.run(refresh(auth=auth, refresh_token_cookie=None, body=None))

    assert auth.refresh_tokens == []


def test_get_user_from_token_requires_access_cookie():
    auth = FakeSessionAuth(sample_user=None)

    with pytest.raises(NotAuthorized, match="No Access Token provided"):
        asyncio.run(
            getUserFromToken(
                access_token=None,
                refresh_token="refresh-token",
                auth=auth,
            ),
        )

    assert auth.access_refresh_pairs == []


def test_get_user_from_token_requires_refresh_cookie():
    auth = FakeSessionAuth(sample_user=None)

    with pytest.raises(NotAuthorized, match="No Refresh Token provided"):
        asyncio.run(
            getUserFromToken(
                access_token="access-token",
                refresh_token=None,
                auth=auth,
            ),
        )

    assert auth.access_refresh_pairs == []


def test_get_user_from_token_passes_cookie_pair_to_auth(sample_user):
    auth = FakeSessionAuth(sample_user)

    user = asyncio.run(
        getUserFromToken(
            access_token="access-token",
            refresh_token="refresh-token",
            auth=auth,
        ),
    )

    assert user == sample_user
    assert auth.access_refresh_pairs == [("access-token", "refresh-token")]


def test_login_sets_access_and_refresh_cookies():
    response = Response()
    auth = FakeCookieIssuingAuth("loginUser")

    result = asyncio.run(
        login(
            request=LoginRequest(email="user@example.com", password="StrongPass1!"),
            response=response,
            auth=auth,
        ),
    )

    assert result.status == "success"
    assert len(auth.payloads) == 1
    _assert_auth_cookies(_set_cookie_headers(response))


def test_register_sets_access_and_refresh_cookies():
    response = Response()
    auth = FakeCookieIssuingAuth("registerUser")

    result = asyncio.run(
        register(
            request=RegisterRequest(
                email="user@example.com",
                password="StrongPass1!",
                dateOfBirth=datetime(1990, 1, 1, tzinfo=timezone.utc),
                firstName="Ada",
                lastName="Lovelace",
                phoneNumber="5551234567",
            ),
            response=response,
            auth=auth,
        ),
    )

    assert result.status == "success"
    assert len(auth.payloads) == 1
    _assert_auth_cookies(_set_cookie_headers(response))
