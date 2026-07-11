import asyncio
from datetime import datetime, timezone

import pytest
from fastapi import Response  # type: ignore

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


def _assert_auth_cookies(response: Response) -> None:
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


def test_refresh_cookie_takes_precedence_over_body_token():
    seen_tokens: list[str] = []

    class FakeAuth:
        def generateAccessTokenFromRefreshToken(self, refresh_token: str) -> Token:
            seen_tokens.append(refresh_token)
            return Token(accessToken="new-access", tokenType="ACCESS_TOKEN")

    result = asyncio.run(
        refresh(
            auth=FakeAuth(),
            refresh_token_cookie="cookie-refresh",
            body=RefreshRequest(refresh_token="body-refresh"),
        ),
    )

    assert result == Token(accessToken="new-access", tokenType="ACCESS_TOKEN")
    assert seen_tokens == ["cookie-refresh"]


def test_refresh_uses_body_token_when_cookie_missing():
    seen_tokens: list[str] = []

    class FakeAuth:
        def generateAccessTokenFromRefreshToken(self, refresh_token: str) -> Token:
            seen_tokens.append(refresh_token)
            return Token(accessToken="new-access", tokenType="ACCESS_TOKEN")

    result = asyncio.run(
        refresh(
            auth=FakeAuth(),
            refresh_token_cookie=None,
            body=RefreshRequest(refresh_token="body-refresh"),
        ),
    )

    assert result.accessToken == "new-access"
    assert seen_tokens == ["body-refresh"]


def test_refresh_requires_token_from_cookie_or_body():
    class FakeAuth:
        def generateAccessTokenFromRefreshToken(self, _refresh_token: str) -> Token:
            pytest.fail("refresh should reject before calling auth service")

    with pytest.raises(CredentialException, match="No Refresh Token provided"):
        asyncio.run(refresh(auth=FakeAuth(), refresh_token_cookie=None, body=None))


def test_get_user_from_token_requires_access_cookie():
    class FakeAuth:
        async def getUserFromAccessToken(self, _access_token: str, _refresh_token: str):
            pytest.fail("missing access cookie should reject before auth service")

    with pytest.raises(NotAuthorized, match="No Access Token provided"):
        asyncio.run(
            getUserFromToken(
                access_token=None,
                refresh_token="refresh-token",
                auth=FakeAuth(),
            ),
        )


def test_get_user_from_token_requires_refresh_cookie():
    class FakeAuth:
        async def getUserFromAccessToken(self, _access_token: str, _refresh_token: str):
            pytest.fail("missing refresh cookie should reject before auth service")

    with pytest.raises(NotAuthorized, match="No Refresh Token provided"):
        asyncio.run(
            getUserFromToken(
                access_token="access-token",
                refresh_token=None,
                auth=FakeAuth(),
            ),
        )


def test_get_user_from_token_forwards_cookie_pair(sample_user):
    seen_tokens: list[tuple[str, str]] = []

    class FakeAuth:
        async def getUserFromAccessToken(
            self,
            access_token: str,
            refresh_token: str,
        ):
            seen_tokens.append((access_token, refresh_token))
            return sample_user

    result = asyncio.run(
        getUserFromToken(
            access_token="access-token",
            refresh_token="refresh-token",
            auth=FakeAuth(),
        ),
    )

    assert result == sample_user
    assert seen_tokens == [("access-token", "refresh-token")]


def test_login_sets_secure_httponly_auth_cookies():
    class FakeAuth:
        async def loginUser(self, request_obj: LoginRequest):
            assert request_obj.email == "user@example.com"
            return (
                Token(accessToken="access-token", tokenType="ACCESS_TOKEN"),
                Token(accessToken="refresh-token", tokenType="REFRESH_TOKEN"),
            )

    response = Response()
    result = asyncio.run(
        login(
            LoginRequest(email="user@example.com", password="Correct-Horse-1!"),
            response,
            auth=FakeAuth(),
        ),
    )

    assert result.message == "Login successful"
    assert result.status == "success"
    _assert_auth_cookies(response)


def test_register_sets_secure_httponly_auth_cookies():
    class FakeAuth:
        async def registerUser(self, request_obj: RegisterRequest):
            assert request_obj.email == "user@example.com"
            return (
                Token(accessToken="access-token", tokenType="ACCESS_TOKEN"),
                Token(accessToken="refresh-token", tokenType="REFRESH_TOKEN"),
            )

    response = Response()
    result = asyncio.run(
        register(
            RegisterRequest(
                email="user@example.com",
                password="Correct-Horse-1!",
                dateOfBirth=datetime(1990, 1, 1, tzinfo=timezone.utc),
                firstName="Ada",
                lastName="Lovelace",
                phoneNumber="+15555550123",
            ),
            response,
            auth=FakeAuth(),
        ),
    )

    assert result.message == "Register successful"
    assert result.status == "success"
    _assert_auth_cookies(response)
