import asyncio
from datetime import UTC, datetime
from http.cookies import Morsel, SimpleCookie

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


def _set_cookies(response: Response) -> dict[str, Morsel[str]]:
    cookies: dict[str, Morsel[str]] = {}
    for name, value in response.raw_headers:
        if name.lower() != b"set-cookie":
            continue
        parsed = SimpleCookie()
        parsed.load(value.decode("latin-1"))
        cookies.update(parsed)
    return cookies


class FakeCookieAuth:
    async def loginUser(self, request: LoginRequest) -> tuple[Token, Token]:
        assert request.email == "user@example.com"
        return (
            Token(accessToken="access-from-login", tokenType="ACCESS_TOKEN"),
            Token(accessToken="refresh-from-login", tokenType="REFRESH_TOKEN"),
        )

    async def registerUser(self, request: RegisterRequest) -> tuple[Token, Token]:
        assert request.email == "new@example.com"
        return (
            Token(accessToken="access-from-register", tokenType="ACCESS_TOKEN"),
            Token(accessToken="refresh-from-register", tokenType="REFRESH_TOKEN"),
        )


def test_login_sets_http_only_secure_access_and_refresh_cookies() -> None:
    response = Response()

    result = asyncio.run(
        login(
            LoginRequest(email="user@example.com", password="ValidPass1!"),
            response,
            auth=FakeCookieAuth(),
        ),
    )

    cookies = _set_cookies(response)
    assert result.model_dump() == {"message": "Login successful", "status": "success"}
    assert cookies["access_token"].value == "access-from-login"
    assert cookies["access_token"]["httponly"]
    assert cookies["access_token"]["secure"]
    assert cookies["access_token"]["max-age"] == "1800"
    assert cookies["refresh_token"].value == "refresh-from-login"
    assert cookies["refresh_token"]["httponly"]
    assert cookies["refresh_token"]["secure"]
    assert cookies["refresh_token"]["max-age"] == str(3600 * 24 * 5)


def test_register_sets_http_only_secure_access_and_refresh_cookies() -> None:
    response = Response()

    result = asyncio.run(
        register(
            RegisterRequest(
                email="new@example.com",
                password="ValidPass1!",
                dateOfBirth=datetime(1990, 1, 1, tzinfo=UTC),
                firstName="Ada",
                lastName="Lovelace",
                phoneNumber="+1 555 123 4567",
            ),
            response,
            auth=FakeCookieAuth(),
        ),
    )

    cookies = _set_cookies(response)
    assert result.model_dump() == {
        "message": "Register successful",
        "status": "success",
    }
    assert cookies["access_token"].value == "access-from-register"
    assert cookies["access_token"]["httponly"]
    assert cookies["access_token"]["secure"]
    assert cookies["refresh_token"].value == "refresh-from-register"
    assert cookies["refresh_token"]["httponly"]
    assert cookies["refresh_token"]["secure"]


def test_refresh_prefers_cookie_token_over_body_token() -> None:
    class FakeAuth:
        seen_tokens: list[str]

        def __init__(self) -> None:
            self.seen_tokens = []

        def generateAccessTokenFromRefreshToken(self, refresh_token: str) -> Token:
            self.seen_tokens.append(refresh_token)
            return Token(
                accessToken=f"access-for-{refresh_token}",
                tokenType="ACCESS_TOKEN",
            )

    auth = FakeAuth()

    result = asyncio.run(
        refresh(
            auth=auth,
            refresh_token_cookie="cookie-token",
            body=RefreshRequest(refresh_token="body-token"),
        ),
    )

    assert result == Token(
        accessToken="access-for-cookie-token",
        tokenType="ACCESS_TOKEN",
    )
    assert auth.seen_tokens == ["cookie-token"]


def test_refresh_rejects_missing_cookie_and_body_token() -> None:
    with pytest.raises(CredentialException, match="No Refresh Token provided"):
        asyncio.run(refresh(auth=object(), refresh_token_cookie=None, body=None))


def test_get_user_from_token_requires_both_cookies() -> None:
    with pytest.raises(NotAuthorized, match="No Access Token provided"):
        asyncio.run(
            getUserFromToken(
                access_token=None,
                refresh_token="refresh-token",
                auth=object(),
            ),
        )

    with pytest.raises(NotAuthorized, match="No Refresh Token provided"):
        asyncio.run(
            getUserFromToken(
                access_token="access-token",
                refresh_token=None,
                auth=object(),
            ),
        )


def test_get_user_from_token_passes_cookie_tokens_to_service() -> None:
    expected_user = UserModel(
        email="user@example.com",
        sub="user-123",
        userFirstName="Ada",
        userLastName="Lovelace",
        phoneNumber="+1 555 123 4567",
        dateOfBirth=datetime(1990, 1, 1, tzinfo=UTC),
        createdAt=datetime(2025, 1, 1, tzinfo=UTC),
        isActive=True,
        subscriptionType="free",
    )

    class FakeAuth:
        seen_tokens: tuple[str, str] | None = None

        async def getUserFromAccessToken(
            self,
            access_token: str,
            refresh_token: str,
        ) -> UserModel:
            self.seen_tokens = (access_token, refresh_token)
            return expected_user

    auth = FakeAuth()

    result = asyncio.run(
        getUserFromToken(
            access_token="access-cookie",
            refresh_token="refresh-cookie",
            auth=auth,
        ),
    )

    assert result == expected_user
    assert auth.seen_tokens == ("access-cookie", "refresh-cookie")
