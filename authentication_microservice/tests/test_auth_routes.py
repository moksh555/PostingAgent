import asyncio

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


class FakeAuth:
    def __init__(self, user=None):
        self.calls = []
        self.user = user

    async def loginUser(self, request):
        self.calls.append(("login", request))
        return (
            Token(accessToken="access-login-token", tokenType="ACCESS_TOKEN"),
            Token(accessToken="refresh-login-token", tokenType="REFRESH_TOKEN"),
        )

    async def registerUser(self, request):
        self.calls.append(("register", request))
        return (
            Token(accessToken="access-register-token", tokenType="ACCESS_TOKEN"),
            Token(accessToken="refresh-register-token", tokenType="REFRESH_TOKEN"),
        )

    def generateAccessTokenFromRefreshToken(self, refresh_token):
        self.calls.append(("refresh", refresh_token))
        return Token(
            accessToken=f"access-from-{refresh_token}",
            tokenType="ACCESS_TOKEN",
        )

    async def getUserFromAccessToken(self, access_token, refresh_token):
        self.calls.append(("get_user", access_token, refresh_token))
        return self.user


def set_cookie_headers(response: Response) -> list[str]:
    return [
        value.decode()
        for key, value in response.raw_headers
        if key.lower() == b"set-cookie"
    ]


def test_login_sets_http_only_secure_access_and_refresh_cookies():
    request = LoginRequest(email="USER@EXAMPLE.COM", password="Password!123")
    response = Response()
    auth = FakeAuth()

    result = asyncio.run(login(request=request, response=response, auth=auth))

    assert result.message == "Login successful"
    assert result.status == "success"
    cookies = set_cookie_headers(response)
    assert any(
        "refresh_token=refresh-login-token" in cookie
        and "HttpOnly" in cookie
        and "Secure" in cookie
        and "Max-Age=432000" in cookie
        for cookie in cookies
    )
    assert any(
        "access_token=access-login-token" in cookie
        and "HttpOnly" in cookie
        and "Secure" in cookie
        and "Max-Age=1800" in cookie
        for cookie in cookies
    )


def test_register_sets_http_only_secure_access_and_refresh_cookies():
    request = RegisterRequest(
        email="new@example.com",
        password="Password!123",
        dateOfBirth="1990-01-01T00:00:00Z",
        firstName="New",
        lastName="User",
        phoneNumber="+15555550123",
    )
    response = Response()
    auth = FakeAuth()

    result = asyncio.run(register(request=request, response=response, auth=auth))

    assert result.message == "Register successful"
    assert result.status == "success"
    cookies = set_cookie_headers(response)
    assert any(
        "refresh_token=refresh-register-token" in cookie
        and "HttpOnly" in cookie
        and "Secure" in cookie
        and "Max-Age=432000" in cookie
        for cookie in cookies
    )
    assert any(
        "access_token=access-register-token" in cookie
        and "HttpOnly" in cookie
        and "Secure" in cookie
        and "Max-Age=1800" in cookie
        for cookie in cookies
    )


def test_refresh_uses_refresh_cookie_before_json_body():
    auth = FakeAuth()

    result = asyncio.run(
        refresh(
            auth=auth,
            refresh_token_cookie="cookie-token",
            body=RefreshRequest(refresh_token="body-token"),
        )
    )

    assert result.accessToken == "access-from-cookie-token"
    assert auth.calls == [("refresh", "cookie-token")]


def test_refresh_uses_json_body_when_cookie_missing():
    auth = FakeAuth()

    result = asyncio.run(
        refresh(
            auth=auth,
            refresh_token_cookie=None,
            body=RefreshRequest(refresh_token="body-token"),
        )
    )

    assert result.accessToken == "access-from-body-token"
    assert auth.calls == [("refresh", "body-token")]


def test_refresh_requires_token_from_cookie_or_body():
    with pytest.raises(CredentialException):
        asyncio.run(refresh(auth=FakeAuth(), refresh_token_cookie=None, body=None))


def test_get_user_from_token_requires_access_cookie():
    with pytest.raises(NotAuthorized, match="No Access Token"):
        asyncio.run(
            getUserFromToken(
                access_token=None,
                refresh_token="refresh-token",
                auth=FakeAuth(),
            )
        )


def test_get_user_from_token_requires_refresh_cookie():
    with pytest.raises(NotAuthorized, match="No Refresh Token"):
        asyncio.run(
            getUserFromToken(
                access_token="access-token",
                refresh_token=None,
                auth=FakeAuth(),
            )
        )


def test_get_user_from_token_passes_cookie_tokens_to_auth(sample_user):
    auth = FakeAuth(user=sample_user)

    result = asyncio.run(
        getUserFromToken(
            access_token="access-token",
            refresh_token="refresh-token",
            auth=auth,
        )
    )

    assert result == sample_user
    assert auth.calls == [("get_user", "access-token", "refresh-token")]
