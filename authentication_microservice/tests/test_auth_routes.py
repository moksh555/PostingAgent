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
from app.models.userModel import UserModel


class FakeAuth:
    def __init__(self):
        self.refresh_inputs: list[str] = []
        self.access_cookie_inputs: list[tuple[str, str]] = []

    async def loginUser(self, _payload):
        return (
            Token(accessToken="access-token", tokenType="ACCESS_TOKEN"),
            Token(accessToken="refresh-token", tokenType="REFRESH_TOKEN"),
        )

    async def registerUser(self, _payload):
        return (
            Token(accessToken="access-token", tokenType="ACCESS_TOKEN"),
            Token(accessToken="refresh-token", tokenType="REFRESH_TOKEN"),
        )

    def generateAccessTokenFromRefreshToken(self, refresh_token: str):
        self.refresh_inputs.append(refresh_token)
        return Token(accessToken="new-access-token", tokenType="ACCESS_TOKEN")

    async def getUserFromAccessToken(self, access_token: str, refresh_token: str):
        self.access_cookie_inputs.append((access_token, refresh_token))
        return UserModel(
            email="user@example.com",
            sub="user-1",
            userFirstName="test",
            userLastName="user",
            phoneNumber="12345678",
            dateOfBirth=datetime(1990, 1, 1, tzinfo=UTC),
            createdAt=datetime(2026, 1, 1, tzinfo=UTC),
            isActive=True,
            subscriptionType="free",
        )


def _set_cookie_headers(response: Response) -> list[str]:
    return [
        value.decode("latin-1")
        for key, value in response.raw_headers
        if key == b"set-cookie"
    ]


def test_refresh_prefers_http_only_cookie_over_body_token():
    auth = FakeAuth()

    token = asyncio.run(
        refresh(
            auth=auth,
            refresh_token_cookie="cookie-refresh",
            body=RefreshRequest(refresh_token="body-refresh"),
        )
    )

    assert token.accessToken == "new-access-token"
    assert auth.refresh_inputs == ["cookie-refresh"]


def test_refresh_uses_body_token_when_cookie_missing():
    auth = FakeAuth()

    asyncio.run(
        refresh(
            auth=auth,
            refresh_token_cookie=None,
            body=RefreshRequest(refresh_token="body-refresh"),
        )
    )

    assert auth.refresh_inputs == ["body-refresh"]


def test_refresh_requires_some_refresh_token():
    with pytest.raises(CredentialException, match="No Refresh Token provided"):
        asyncio.run(refresh(auth=FakeAuth(), refresh_token_cookie=None, body=None))


def test_login_sets_secure_http_only_access_and_refresh_cookies():
    response = Response()

    result = asyncio.run(
        login(
            request=LoginRequest(email="user@example.com", password="Password1!x"),
            response=response,
            auth=FakeAuth(),
        )
    )

    cookies = _set_cookie_headers(response)
    assert result.status == "success"
    assert any("refresh_token=refresh-token" in cookie for cookie in cookies)
    assert any("access_token=access-token" in cookie for cookie in cookies)
    assert all("HttpOnly" in cookie and "Secure" in cookie for cookie in cookies)


def test_register_sets_secure_http_only_access_and_refresh_cookies():
    response = Response()

    result = asyncio.run(
        register(
            request=RegisterRequest(
                email="user@example.com",
                password="Password1!x",
                dateOfBirth=datetime(1990, 1, 1, tzinfo=UTC),
                firstName="Test",
                lastName="User",
                phoneNumber="12345678",
            ),
            response=response,
            auth=FakeAuth(),
        )
    )

    cookies = _set_cookie_headers(response)
    assert result.status == "success"
    assert any("refresh_token=refresh-token" in cookie for cookie in cookies)
    assert any("access_token=access-token" in cookie for cookie in cookies)
    assert all("HttpOnly" in cookie and "Secure" in cookie for cookie in cookies)


def test_get_user_from_token_requires_both_cookies():
    with pytest.raises(NotAuthorized, match="No Access Token provided"):
        asyncio.run(
            getUserFromToken(
                access_token=None,
                refresh_token="refresh",
                auth=FakeAuth(),
            )
        )
    with pytest.raises(NotAuthorized, match="No Refresh Token provided"):
        asyncio.run(
            getUserFromToken(
                access_token="access",
                refresh_token=None,
                auth=FakeAuth(),
            )
        )


def test_get_user_from_token_passes_cookie_pair_to_service():
    auth = FakeAuth()

    user = asyncio.run(
        getUserFromToken(
            access_token="access-cookie",
            refresh_token="refresh-cookie",
            auth=auth,
        )
    )

    assert user.sub == "user-1"
    assert auth.access_cookie_inputs == [("access-cookie", "refresh-cookie")]
