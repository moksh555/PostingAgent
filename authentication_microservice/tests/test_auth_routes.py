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
from app.models.userModel import UserModel


def _set_cookie_headers(response: Response) -> list[str]:
    return [
        value.decode("latin-1")
        for name, value in response.raw_headers
        if name == b"set-cookie"
    ]


def _user() -> UserModel:
    return UserModel(
        email="person@example.com",
        sub="user-123",
        userFirstName="Test",
        userLastName="User",
        phoneNumber="+15555550123",
        dateOfBirth=datetime(1990, 1, 1, tzinfo=timezone.utc),
        createdAt=datetime(2026, 1, 1, tzinfo=timezone.utc),
        isActive=True,
        subscriptionType="free",
    )


def test_refresh_prefers_httponly_cookie_over_body_token():
    class FakeAuth:
        def __init__(self):
            self.calls: list[str] = []

        def generateAccessTokenFromRefreshToken(self, refresh_token: str) -> Token:
            self.calls.append(refresh_token)
            return Token(accessToken="new-access-token", tokenType="ACCESS_TOKEN")

    auth = FakeAuth()

    result = asyncio.run(
        refresh(
            auth=auth,
            refresh_token_cookie="cookie-refresh-token",
            body=RefreshRequest(refresh_token="body-refresh-token"),
        )
    )

    assert result.accessToken == "new-access-token"
    assert auth.calls == ["cookie-refresh-token"]


def test_refresh_uses_body_token_when_cookie_is_absent():
    class FakeAuth:
        def __init__(self):
            self.calls: list[str] = []

        def generateAccessTokenFromRefreshToken(self, refresh_token: str) -> Token:
            self.calls.append(refresh_token)
            return Token(accessToken="new-access-token", tokenType="ACCESS_TOKEN")

    auth = FakeAuth()

    result = asyncio.run(
        refresh(
            auth=auth,
            refresh_token_cookie=None,
            body=RefreshRequest(refresh_token="body-refresh-token"),
        )
    )

    assert result.accessToken == "new-access-token"
    assert auth.calls == ["body-refresh-token"]


def test_refresh_requires_cookie_or_body_token():
    with pytest.raises(CredentialException, match="No Refresh Token provided"):
        asyncio.run(refresh(auth=object(), refresh_token_cookie=None, body=None))


def test_get_user_from_token_requires_both_auth_cookies():
    with pytest.raises(NotAuthorized, match="No Access Token provided"):
        asyncio.run(
            getUserFromToken(
                access_token=None,
                refresh_token="refresh-token",
                auth=object(),
            )
        )

    with pytest.raises(NotAuthorized, match="No Refresh Token provided"):
        asyncio.run(
            getUserFromToken(
                access_token="access-token",
                refresh_token=None,
                auth=object(),
            )
        )


def test_get_user_from_token_forwards_cookie_pair_to_auth_service():
    class FakeAuth:
        def __init__(self):
            self.calls: list[tuple[str, str]] = []

        async def getUserFromAccessToken(
            self,
            access_token: str,
            refresh_token: str,
        ) -> UserModel:
            self.calls.append((access_token, refresh_token))
            return _user()

    auth = FakeAuth()

    result = asyncio.run(
        getUserFromToken(
            access_token="access-token",
            refresh_token="refresh-token",
            auth=auth,
        )
    )

    assert result.sub == "user-123"
    assert auth.calls == [("access-token", "refresh-token")]


@pytest.mark.parametrize(
    ("route_call", "payload"),
    [
        (
            login,
            LoginRequest(email="person@example.com", password="correct horse battery"),
        ),
        (
            register,
            RegisterRequest(
                email="person@example.com",
                password="correct horse battery",
                dateOfBirth=datetime(1990, 1, 1, tzinfo=timezone.utc),
                firstName="Test",
                lastName="User",
                phoneNumber="+15555550123",
            ),
        ),
    ],
)
def test_login_and_register_set_secure_httponly_auth_cookies(route_call, payload):
    class FakeAuth:
        async def loginUser(self, request_payload):
            return self._tokens()

        async def registerUser(self, request_payload):
            return self._tokens()

        def _tokens(self) -> tuple[Token, Token]:
            return (
                Token(accessToken="access-token-value", tokenType="ACCESS_TOKEN"),
                Token(accessToken="refresh-token-value", tokenType="REFRESH_TOKEN"),
            )

    response = Response()

    result = asyncio.run(route_call(request=payload, response=response, auth=FakeAuth()))
    cookies = _set_cookie_headers(response)

    assert result.status == "success"
    assert any(
        cookie.startswith("access_token=access-token-value")
        and "HttpOnly" in cookie
        and "Secure" in cookie
        and "Max-Age=1800" in cookie
        for cookie in cookies
    )
    assert any(
        cookie.startswith("refresh_token=refresh-token-value")
        and "HttpOnly" in cookie
        and "Secure" in cookie
        and "Max-Age=432000" in cookie
        for cookie in cookies
    )
