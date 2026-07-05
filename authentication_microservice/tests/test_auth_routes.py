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
from app.models.tokenModel import RefreshRequest, Token


def _set_cookie_headers(response: Response) -> list[str]:
    return [
        value.decode("latin-1")
        for key, value in response.raw_headers
        if key.lower() == b"set-cookie"
    ]


def _cookie_header(response: Response, name: str) -> str:
    return next(
        header for header in _set_cookie_headers(response) if header.startswith(f"{name}=")
    )


def _assert_secure_http_only_cookie(
    response: Response,
    name: str,
    value: str,
    max_age: int,
):
    header = _cookie_header(response, name)

    assert header.startswith(f"{name}={value};")
    assert "HttpOnly" in header
    assert "Secure" in header
    assert f"Max-Age={max_age}" in header


class FakeSessionAuth:
    async def loginUser(self, request):
        return (
            Token(accessToken="login-access", tokenType="ACCESS_TOKEN"),
            Token(accessToken="login-refresh", tokenType="REFRESH_TOKEN"),
        )

    async def registerUser(self, request):
        return (
            Token(accessToken="register-access", tokenType="ACCESS_TOKEN"),
            Token(accessToken="register-refresh", tokenType="REFRESH_TOKEN"),
        )


def test_login_sets_secure_http_only_session_cookies():
    response = Response()

    result = asyncio.run(
        login(
            LoginRequest(email="person@example.com", password="CorrectPass1!"),
            response,
            auth=FakeSessionAuth(),
        ),
    )

    assert result.status == "success"
    _assert_secure_http_only_cookie(
        response,
        "refresh_token",
        "login-refresh",
        max_age=3600 * 24 * 5,
    )
    _assert_secure_http_only_cookie(
        response,
        "access_token",
        "login-access",
        max_age=1800,
    )


def test_register_sets_secure_http_only_session_cookies(valid_register_request):
    response = Response()

    result = asyncio.run(
        register(valid_register_request, response, auth=FakeSessionAuth()),
    )

    assert result.status == "success"
    _assert_secure_http_only_cookie(
        response,
        "refresh_token",
        "register-refresh",
        max_age=3600 * 24 * 5,
    )
    _assert_secure_http_only_cookie(
        response,
        "access_token",
        "register-access",
        max_age=1800,
    )


def test_refresh_uses_cookie_token_before_body_token():
    observed = {}

    class FakeAuth:
        def generateAccessTokenFromRefreshToken(self, refresh_token):
            observed["refresh_token"] = refresh_token
            return Token(accessToken="new-access", tokenType="ACCESS_TOKEN")

    result = asyncio.run(
        refresh(
            auth=FakeAuth(),
            refresh_token_cookie="cookie-token",
            body=RefreshRequest(refresh_token="body-token"),
        ),
    )

    assert result == Token(accessToken="new-access", tokenType="ACCESS_TOKEN")
    assert observed == {"refresh_token": "cookie-token"}


def test_refresh_falls_back_to_body_token_when_cookie_missing():
    observed = {}

    class FakeAuth:
        def generateAccessTokenFromRefreshToken(self, refresh_token):
            observed["refresh_token"] = refresh_token
            return Token(accessToken="new-access", tokenType="ACCESS_TOKEN")

    result = asyncio.run(
        refresh(
            auth=FakeAuth(),
            refresh_token_cookie=None,
            body=RefreshRequest(refresh_token="body-token"),
        ),
    )

    assert result == Token(accessToken="new-access", tokenType="ACCESS_TOKEN")
    assert observed == {"refresh_token": "body-token"}


def test_refresh_requires_a_refresh_token():
    with pytest.raises(CredentialException, match="No Refresh Token provided"):
        asyncio.run(refresh(auth=object(), refresh_token_cookie=None, body=None))


def test_get_user_from_token_requires_access_cookie():
    with pytest.raises(NotAuthorized, match="No Access Token provided"):
        asyncio.run(getUserFromToken(access_token=None, refresh_token="refresh", auth=object()))


def test_get_user_from_token_requires_refresh_cookie():
    with pytest.raises(NotAuthorized, match="No Refresh Token provided"):
        asyncio.run(getUserFromToken(access_token="access", refresh_token=None, auth=object()))


def test_get_user_from_token_forwards_cookie_pair_to_auth_service(user_model):
    observed = {}

    class FakeAuth:
        async def getUserFromAccessToken(self, access_token, refresh_token):
            observed["access_token"] = access_token
            observed["refresh_token"] = refresh_token
            return user_model

    result = asyncio.run(
        getUserFromToken(
            access_token="access-cookie",
            refresh_token="refresh-cookie",
            auth=FakeAuth(),
        ),
    )

    assert result == user_model
    assert observed == {
        "access_token": "access-cookie",
        "refresh_token": "refresh-cookie",
    }
