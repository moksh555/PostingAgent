import asyncio
from datetime import UTC, datetime

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


def _set_cookie_headers(response: Response) -> list[str]:
    return [
        value.decode("latin-1")
        for key, value in response.raw_headers
        if key == b"set-cookie"
    ]


def _assert_auth_cookies(response: Response) -> None:
    cookie_headers = _set_cookie_headers(response)
    assert any(
        "refresh_token=refresh-token" in header
        and "HttpOnly" in header
        and "Secure" in header
        and "Max-Age=432000" in header
        for header in cookie_headers
    )
    assert any(
        "access_token=access-token" in header
        and "HttpOnly" in header
        and "Secure" in header
        and "Max-Age=1800" in header
        for header in cookie_headers
    )


class LoginRegisterAuthStub:
    def __init__(self) -> None:
        self.calls: list[tuple[str, object]] = []

    async def loginUser(self, request):
        self.calls.append(("login", request))
        return (
            Token(accessToken="access-token", tokenType="ACCESS_TOKEN"),
            Token(accessToken="refresh-token", tokenType="REFRESH_TOKEN"),
        )

    async def registerUser(self, request):
        self.calls.append(("register", request))
        return (
            Token(accessToken="access-token", tokenType="ACCESS_TOKEN"),
            Token(accessToken="refresh-token", tokenType="REFRESH_TOKEN"),
        )


@pytest.mark.parametrize(
    ("route_func", "request", "call_name", "message"),
    [
        (
            login_route.login,
            LoginRequest(email="User@Example.com", password="StrongPass123!"),
            "login",
            "Login successful",
        ),
        (
            register_route.register,
            RegisterRequest(
                email="user@example.com",
                password="StrongPass123!",
                dateOfBirth=datetime(1990, 1, 1, tzinfo=UTC),
                firstName="Test",
                lastName="User",
                phoneNumber="+15555550123",
            ),
            "register",
            "Register successful",
        ),
    ],
)
def test_login_and_register_set_secure_access_and_refresh_cookies(
    route_func,
    request,
    call_name,
    message,
):
    response = Response()
    auth = LoginRegisterAuthStub()

    result = asyncio.run(route_func(request=request, response=response, auth=auth))

    assert result.message == message
    assert result.status == "success"
    assert auth.calls == [(call_name, request)]
    _assert_auth_cookies(response)


def test_refresh_prefers_http_only_cookie_over_body_token():
    class AuthStub:
        def __init__(self) -> None:
            self.seen_token: str | None = None

        def generateAccessTokenFromRefreshToken(self, token: str):
            self.seen_token = token
            return Token(accessToken=f"access-for-{token}", tokenType="ACCESS_TOKEN")

    auth = AuthStub()

    result = asyncio.run(
        refresh_route.refresh(
            auth=auth,
            refresh_token_cookie="cookie-token",
            body=RefreshRequest(refresh_token="body-token"),
        )
    )

    assert auth.seen_token == "cookie-token"
    assert result == Token(accessToken="access-for-cookie-token", tokenType="ACCESS_TOKEN")


def test_refresh_uses_body_token_when_cookie_is_missing():
    class AuthStub:
        def __init__(self) -> None:
            self.seen_token: str | None = None

        def generateAccessTokenFromRefreshToken(self, token: str):
            self.seen_token = token
            return Token(accessToken="new-access", tokenType="ACCESS_TOKEN")

    auth = AuthStub()

    result = asyncio.run(
        refresh_route.refresh(
            auth=auth,
            refresh_token_cookie=None,
            body=RefreshRequest(refresh_token="body-token"),
        )
    )

    assert auth.seen_token == "body-token"
    assert result == Token(accessToken="new-access", tokenType="ACCESS_TOKEN")


def test_refresh_requires_token_from_cookie_or_body():
    class AuthStub:
        def generateAccessTokenFromRefreshToken(self, token: str):
            raise AssertionError("missing token should not call auth service")

    with pytest.raises(CredentialException, match="No Refresh Token provided"):
        asyncio.run(refresh_route.refresh(auth=AuthStub(), refresh_token_cookie=None, body=None))


def test_get_user_from_token_requires_both_cookies(sample_user):
    class AuthStub:
        async def getUserFromAccessToken(self, access_token: str, refresh_token: str):
            raise AssertionError("missing cookies should not call auth service")

    with pytest.raises(NotAuthorized, match="No Access Token provided"):
        asyncio.run(
            get_user_route.getUserFromToken(
                access_token=None,
                refresh_token="refresh-token",
                auth=AuthStub(),
            )
        )
    with pytest.raises(NotAuthorized, match="No Refresh Token provided"):
        asyncio.run(
            get_user_route.getUserFromToken(
                access_token="access-token",
                refresh_token=None,
                auth=AuthStub(),
            )
        )


def test_get_user_from_token_delegates_cookie_tokens_to_auth_service(sample_user):
    class AuthStub:
        def __init__(self) -> None:
            self.seen_tokens: tuple[str, str] | None = None

        async def getUserFromAccessToken(self, access_token: str, refresh_token: str):
            self.seen_tokens = (access_token, refresh_token)
            return sample_user

    auth = AuthStub()

    result = asyncio.run(
        get_user_route.getUserFromToken(
            access_token="access-token",
            refresh_token="refresh-token",
            auth=auth,
        )
    )

    assert result == sample_user
    assert auth.seen_tokens == ("access-token", "refresh-token")
