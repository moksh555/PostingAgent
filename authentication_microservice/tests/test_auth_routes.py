"""Route contract tests for cookie-based authentication flows."""

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
        self.user_token_inputs: list[tuple[str, str]] = []

    def generateAccessTokenFromRefreshToken(self, token: str) -> Token:
        self.refresh_inputs.append(token)
        return Token(accessToken=f"access-for-{token}", tokenType="ACCESS_TOKEN")

    async def getUserFromAccessToken(
        self,
        access_token: str,
        refresh_token: str,
    ) -> UserModel:
        self.user_token_inputs.append((access_token, refresh_token))
        return UserModel(
            sub="user-123",
            email="person@example.com",
            userFirstName="person",
            userLastName="example",
            phoneNumber="+1 555 123 4567",
            dateOfBirth=datetime(1990, 1, 1, tzinfo=UTC),
            createdAt=datetime(2026, 1, 1, tzinfo=UTC),
            isActive=True,
            subscriptionType="free",
        )

    async def loginUser(self, _request):
        return (
            Token(accessToken="signed-access", tokenType="ACCESS_TOKEN"),
            Token(accessToken="signed-refresh", tokenType="REFRESH_TOKEN"),
        )

    async def registerUser(self, _request):
        return (
            Token(accessToken="signed-access", tokenType="ACCESS_TOKEN"),
            Token(accessToken="signed-refresh", tokenType="REFRESH_TOKEN"),
        )


def _cookie_headers(response: Response) -> list[str]:
    return response.headers.getlist("set-cookie")


def _assert_secure_auth_cookies(response: Response) -> None:
    cookies = _cookie_headers(response)
    assert len(cookies) == 2
    refresh_cookie = next(cookie for cookie in cookies if cookie.startswith("refresh_token="))
    access_cookie = next(cookie for cookie in cookies if cookie.startswith("access_token="))
    assert "signed-refresh" in refresh_cookie
    assert "HttpOnly" in refresh_cookie
    assert "Secure" in refresh_cookie
    assert "Max-Age=432000" in refresh_cookie
    assert "signed-access" in access_cookie
    assert "HttpOnly" in access_cookie
    assert "Secure" in access_cookie
    assert "Max-Age=1800" in access_cookie


def test_refresh_cookie_takes_precedence_over_request_body():
    auth = FakeAuth()

    result = asyncio.run(
        refresh(
            auth=auth,  # type: ignore[arg-type]
            refresh_token_cookie="cookie-token",
            body=RefreshRequest(refresh_token="body-token"),
        ),
    )

    assert result.accessToken == "access-for-cookie-token"
    assert auth.refresh_inputs == ["cookie-token"]


def test_refresh_accepts_json_body_fallback():
    auth = FakeAuth()

    result = asyncio.run(
        refresh(
            auth=auth,  # type: ignore[arg-type]
            refresh_token_cookie=None,
            body=RefreshRequest(refresh_token="body-token"),
        ),
    )

    assert result.accessToken == "access-for-body-token"
    assert auth.refresh_inputs == ["body-token"]


def test_refresh_requires_a_token():
    with pytest.raises(CredentialException, match="No Refresh Token provided"):
        asyncio.run(
            refresh(
                auth=FakeAuth(),  # type: ignore[arg-type]
                refresh_token_cookie=None,
                body=None,
            ),
        )


def test_get_user_from_token_requires_both_cookies():
    auth = FakeAuth()

    with pytest.raises(NotAuthorized, match="No Access Token"):
        asyncio.run(
            getUserFromToken(
                access_token=None,
                refresh_token="refresh",
                auth=auth,  # type: ignore[arg-type]
            ),
        )
    with pytest.raises(NotAuthorized, match="No Refresh Token"):
        asyncio.run(
            getUserFromToken(
                access_token="access",
                refresh_token=None,
                auth=auth,  # type: ignore[arg-type]
            ),
        )
    assert auth.user_token_inputs == []


def test_get_user_from_token_forwards_cookie_pair():
    auth = FakeAuth()

    result = asyncio.run(
        getUserFromToken(
            access_token="access-cookie",
            refresh_token="refresh-cookie",
            auth=auth,  # type: ignore[arg-type]
        ),
    )

    assert result.sub == "user-123"
    assert auth.user_token_inputs == [("access-cookie", "refresh-cookie")]


def test_login_sets_secure_http_only_auth_cookies():
    response = Response()

    result = asyncio.run(
        login(
            request=LoginRequest(email="person@example.com", password="ValidPass1!"),
            response=response,
            auth=FakeAuth(),  # type: ignore[arg-type]
        ),
    )

    assert result.model_dump() == {"message": "Login successful", "status": "success"}
    _assert_secure_auth_cookies(response)


def test_register_sets_secure_http_only_auth_cookies():
    response = Response()

    result = asyncio.run(
        register(
            request=RegisterRequest(
                email="person@example.com",
                password="ValidPass1!",
                dateOfBirth=datetime(1990, 1, 1, tzinfo=UTC),
                firstName="Person",
                lastName="Example",
                phoneNumber="+1 555 123 4567",
            ),
            response=response,
            auth=FakeAuth(),  # type: ignore[arg-type]
        ),
    )

    assert result.model_dump() == {"message": "Register successful", "status": "success"}
    _assert_secure_auth_cookies(response)
