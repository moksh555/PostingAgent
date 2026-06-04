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


def _user() -> UserModel:
    return UserModel(
        email="person@example.com",
        sub="user-123",
        userFirstName="person",
        userLastName="example",
        phoneNumber="1234567890",
        dateOfBirth=datetime(1990, 1, 1, tzinfo=UTC),
        createdAt=datetime(2024, 1, 1, tzinfo=UTC),
        isActive=True,
        subscriptionType="free",
    )


def _cookie_headers(response: Response) -> list[str]:
    return [
        value.decode("latin-1")
        for key, value in response.raw_headers
        if key == b"set-cookie"
    ]


def _assert_session_cookies(response: Response, access_token: str, refresh_token: str) -> None:
    cookie_headers = _cookie_headers(response)
    assert len(cookie_headers) == 2

    access_cookie = next(header for header in cookie_headers if header.startswith("access_token="))
    refresh_cookie = next(header for header in cookie_headers if header.startswith("refresh_token="))

    assert f"access_token={access_token}" in access_cookie
    assert "httponly" in access_cookie.lower()
    assert "secure" in access_cookie.lower()
    assert "max-age=1800" in access_cookie.lower()

    assert f"refresh_token={refresh_token}" in refresh_cookie
    assert "httponly" in refresh_cookie.lower()
    assert "secure" in refresh_cookie.lower()
    assert "max-age=432000" in refresh_cookie.lower()


class _FakeAuth:
    def __init__(self) -> None:
        self.refresh_tokens: list[str] = []
        self.access_token_pairs: list[tuple[str, str]] = []
        self.login_requests: list[LoginRequest] = []
        self.register_requests: list[RegisterRequest] = []

    def generateAccessTokenFromRefreshToken(self, refresh_token: str) -> Token:
        self.refresh_tokens.append(refresh_token)
        return Token(accessToken=f"access-for-{refresh_token}", tokenType="ACCESS_TOKEN")

    async def getUserFromAccessToken(self, access_token: str, refresh_token: str) -> UserModel:
        self.access_token_pairs.append((access_token, refresh_token))
        return _user()

    async def loginUser(self, request: LoginRequest) -> tuple[Token, Token]:
        self.login_requests.append(request)
        return (
            Token(accessToken="login-access-token", tokenType="ACCESS_TOKEN"),
            Token(accessToken="login-refresh-token", tokenType="REFRESH_TOKEN"),
        )

    async def registerUser(self, request: RegisterRequest) -> tuple[Token, Token]:
        self.register_requests.append(request)
        return (
            Token(accessToken="register-access-token", tokenType="ACCESS_TOKEN"),
            Token(accessToken="register-refresh-token", tokenType="REFRESH_TOKEN"),
        )


class TestRefreshRoute:
    def test_refresh_prefers_cookie_over_body_token(self) -> None:
        auth = _FakeAuth()

        token = asyncio.run(
            refresh(
                auth=auth,
                refresh_token_cookie="cookie-token",
                body=RefreshRequest(refresh_token="body-token"),
            ),
        )

        assert token == Token(accessToken="access-for-cookie-token", tokenType="ACCESS_TOKEN")
        assert auth.refresh_tokens == ["cookie-token"]

    def test_refresh_accepts_body_token_when_cookie_absent(self) -> None:
        auth = _FakeAuth()

        token = asyncio.run(
            refresh(
                auth=auth,
                refresh_token_cookie=None,
                body=RefreshRequest(refresh_token="body-token"),
            ),
        )

        assert token == Token(accessToken="access-for-body-token", tokenType="ACCESS_TOKEN")
        assert auth.refresh_tokens == ["body-token"]

    def test_refresh_requires_cookie_or_body_token(self) -> None:
        with pytest.raises(CredentialException):
            asyncio.run(refresh(auth=_FakeAuth(), refresh_token_cookie=None, body=None))


class TestGetUserFromTokenRoute:
    @pytest.mark.parametrize(
        ("access_token", "refresh_token", "message"),
        [
            (None, "refresh-token", "No Access Token"),
            ("access-token", None, "No Refresh Token"),
        ],
    )
    def test_get_user_from_token_requires_both_cookies(
        self,
        access_token: str | None,
        refresh_token: str | None,
        message: str,
    ) -> None:
        with pytest.raises(NotAuthorized, match=message):
            asyncio.run(
                getUserFromToken(
                    access_token=access_token,
                    refresh_token=refresh_token,
                    auth=_FakeAuth(),
                ),
            )

    def test_get_user_from_token_delegates_cookie_pair_to_auth_service(self) -> None:
        auth = _FakeAuth()

        user = asyncio.run(
            getUserFromToken(
                access_token="access-token",
                refresh_token="refresh-token",
                auth=auth,
            ),
        )

        assert user == _user()
        assert auth.access_token_pairs == [("access-token", "refresh-token")]


class TestLoginAndRegisterCookieContracts:
    def test_login_sets_secure_httponly_session_cookies_and_returns_status_only(self) -> None:
        auth = _FakeAuth()
        response = Response()
        request = LoginRequest(email="person@example.com", password="Secret123!")

        result = asyncio.run(login(request=request, response=response, auth=auth))

        assert result.model_dump() == {"message": "Login successful", "status": "success"}
        assert auth.login_requests == [request]
        _assert_session_cookies(response, "login-access-token", "login-refresh-token")

    def test_register_sets_secure_httponly_session_cookies_and_returns_status_only(self) -> None:
        auth = _FakeAuth()
        response = Response()
        request = RegisterRequest(
            email="person@example.com",
            password="Secret123!",
            dateOfBirth=datetime(1990, 1, 1, tzinfo=UTC),
            firstName="Person",
            lastName="Example",
            phoneNumber="1234567890",
        )

        result = asyncio.run(register(request=request, response=response, auth=auth))

        assert result.model_dump() == {"message": "Register successful", "status": "success"}
        assert auth.register_requests == [request]
        _assert_session_cookies(response, "register-access-token", "register-refresh-token")
