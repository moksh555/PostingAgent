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


def _set_cookie_headers(response: Response) -> list[str]:
    return [
        value.decode("latin-1")
        for name, value in response.raw_headers
        if name.decode("latin-1").lower() == "set-cookie"
    ]


def _assert_session_cookie(
    headers: list[str],
    *,
    name: str,
    value: str,
    max_age: int,
) -> None:
    cookie = next(header for header in headers if header.startswith(f"{name}={value};"))
    assert "HttpOnly" in cookie
    assert "Secure" in cookie
    assert f"Max-Age={max_age}" in cookie


class CookieIssuingAuth:
    async def loginUser(self, request):
        return (
            Token(accessToken="access-token", tokenType="ACCESS_TOKEN"),
            Token(accessToken="refresh-token", tokenType="REFRESH_TOKEN"),
        )

    async def registerUser(self, request):
        return (
            Token(accessToken="access-token", tokenType="ACCESS_TOKEN"),
            Token(accessToken="refresh-token", tokenType="REFRESH_TOKEN"),
        )


@pytest.mark.parametrize(
    ("route_func", "payload", "expected_message"),
    [
        (
            login,
            LoginRequest(email="User@Example.com", password="Password123!"),
            "Login successful",
        ),
        (
            register,
            RegisterRequest(
                email="User@Example.com",
                password="Password123!",
                dateOfBirth=datetime(1990, 1, 1, tzinfo=UTC),
                firstName="Test",
                lastName="User",
                phoneNumber="5551234567",
            ),
            "Register successful",
        ),
    ],
)
def test_login_and_register_issue_secure_session_cookies(
    route_func,
    payload,
    expected_message,
):
    response = Response()

    result = asyncio.run(route_func(payload, response, CookieIssuingAuth()))

    assert result.message == expected_message
    headers = _set_cookie_headers(response)
    _assert_session_cookie(
        headers,
        name="refresh_token",
        value="refresh-token",
        max_age=3600 * 24 * 5,
    )
    _assert_session_cookie(
        headers,
        name="access_token",
        value="access-token",
        max_age=1800,
    )


class RefreshAuth:
    def __init__(self):
        self.calls: list[str] = []

    def generateAccessTokenFromRefreshToken(self, refresh_token: str) -> Token:
        self.calls.append(refresh_token)
        return Token(accessToken=f"access-for-{refresh_token}", tokenType="ACCESS_TOKEN")


def test_refresh_prefers_httponly_cookie_over_body_token():
    auth = RefreshAuth()

    result = asyncio.run(
        refresh(
            auth=auth,
            refresh_token_cookie="cookie-token",
            body=RefreshRequest(refresh_token="body-token"),
        ),
    )

    assert result.accessToken == "access-for-cookie-token"
    assert auth.calls == ["cookie-token"]


def test_refresh_uses_body_token_when_cookie_missing():
    auth = RefreshAuth()

    result = asyncio.run(
        refresh(
            auth=auth,
            refresh_token_cookie=None,
            body=RefreshRequest(refresh_token="body-token"),
        ),
    )

    assert result.accessToken == "access-for-body-token"
    assert auth.calls == ["body-token"]


def test_refresh_requires_some_refresh_token():
    with pytest.raises(CredentialException, match="No Refresh Token provided"):
        asyncio.run(refresh(auth=RefreshAuth(), refresh_token_cookie=None, body=None))


class UserLookupAuth:
    def __init__(self):
        self.calls: list[tuple[str, str]] = []

    async def getUserFromAccessToken(self, access_token: str, refresh_token: str) -> UserModel:
        self.calls.append((access_token, refresh_token))
        return UserModel(
            email="user@example.com",
            sub="user-123",
            userFirstName="Test",
            userLastName="User",
            phoneNumber="5551234567",
            dateOfBirth=datetime(1990, 1, 1, tzinfo=UTC),
            createdAt=datetime(2024, 1, 1, tzinfo=UTC),
            isActive=True,
            subscriptionType="free",
        )


def test_get_user_from_token_requires_both_session_cookies():
    with pytest.raises(NotAuthorized, match="No Access Token provided"):
        asyncio.run(
            getUserFromToken(
                access_token=None,
                refresh_token="refresh-token",
                auth=UserLookupAuth(),
            ),
        )

    with pytest.raises(NotAuthorized, match="No Refresh Token provided"):
        asyncio.run(
            getUserFromToken(
                access_token="access-token",
                refresh_token=None,
                auth=UserLookupAuth(),
            ),
        )


def test_get_user_from_token_delegates_cookie_pair_to_auth_service():
    auth = UserLookupAuth()

    user = asyncio.run(
        getUserFromToken(
            access_token="access-token",
            refresh_token="refresh-token",
            auth=auth,
        ),
    )

    assert user.sub == "user-123"
    assert auth.calls == [("access-token", "refresh-token")]
