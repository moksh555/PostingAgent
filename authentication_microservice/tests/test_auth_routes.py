import asyncio

import pytest
from fastapi import Response

from app.api.version1 import getUserFromToken as user_from_token_route
from app.api.version1 import login as login_route
from app.api.version1 import refresh as refresh_route
from app.api.version1 import register as register_route
from app.errorsHandler.loginError import NotAuthorized
from app.errorsHandler.tokenError import CredentialException
from app.models.loginModel import LoginRequest
from app.models.tokenModel import RefreshRequest, Token


def _set_cookie_headers(response: Response) -> list[str]:
    return [
        value.decode()
        for name, value in response.raw_headers
        if name == b"set-cookie"
    ]


def _cookie_named(cookies: list[str], name: str) -> str:
    return next(cookie for cookie in cookies if cookie.startswith(f"{name}="))


class CookieAuth:
    def __init__(self):
        self.seen_payload = None

    async def loginUser(self, payload):
        self.seen_payload = payload
        return (
            Token(accessToken="access-token", tokenType="ACCESS_TOKEN"),
            Token(accessToken="refresh-token", tokenType="REFRESH_TOKEN"),
        )

    async def registerUser(self, payload):
        self.seen_payload = payload
        return (
            Token(accessToken="access-token", tokenType="ACCESS_TOKEN"),
            Token(accessToken="refresh-token", tokenType="REFRESH_TOKEN"),
        )


def test_login_sets_secure_http_only_access_and_refresh_cookies():
    auth = CookieAuth()
    response = Response()
    payload = LoginRequest(email="person@example.com", password="StrongPass1!")

    result = asyncio.run(login_route.login(payload, response, auth))

    assert result.status == "success"
    assert auth.seen_payload == payload
    cookies = _set_cookie_headers(response)
    access_cookie = _cookie_named(cookies, "access_token")
    refresh_cookie = _cookie_named(cookies, "refresh_token")
    assert "Max-Age=1800" in access_cookie
    assert "HttpOnly" in access_cookie
    assert "Secure" in access_cookie
    assert "Max-Age=432000" in refresh_cookie
    assert "HttpOnly" in refresh_cookie
    assert "Secure" in refresh_cookie


def test_register_sets_secure_http_only_access_and_refresh_cookies(register_payload):
    auth = CookieAuth()
    response = Response()

    result = asyncio.run(register_route.register(register_payload, response, auth))

    assert result.status == "success"
    assert auth.seen_payload == register_payload
    cookies = _set_cookie_headers(response)
    assert "HttpOnly" in _cookie_named(cookies, "access_token")
    assert "Secure" in _cookie_named(cookies, "access_token")
    assert "HttpOnly" in _cookie_named(cookies, "refresh_token")
    assert "Secure" in _cookie_named(cookies, "refresh_token")


class RefreshAuth:
    def __init__(self):
        self.seen_refresh_tokens: list[str] = []

    def generateAccessTokenFromRefreshToken(self, refresh_token: str) -> Token:
        self.seen_refresh_tokens.append(refresh_token)
        return Token(accessToken="new-access-token", tokenType="ACCESS_TOKEN")


def test_refresh_prefers_http_only_cookie_over_body_token():
    auth = RefreshAuth()

    result = asyncio.run(
        refresh_route.refresh(
            auth=auth,
            refresh_token_cookie="cookie-refresh-token",
            body=RefreshRequest(refresh_token="body-refresh-token"),
        ),
    )

    assert result.accessToken == "new-access-token"
    assert auth.seen_refresh_tokens == ["cookie-refresh-token"]


def test_refresh_requires_cookie_or_body_token():
    with pytest.raises(CredentialException):
        asyncio.run(
            refresh_route.refresh(
                auth=RefreshAuth(),
                refresh_token_cookie=None,
                body=RefreshRequest(refresh_token=None),
            ),
        )


class UserFromTokenAuth:
    def __init__(self, returned_user):
        self.returned_user = returned_user
        self.seen_tokens: list[tuple[str, str]] = []

    async def getUserFromAccessToken(self, access_token: str, refresh_token: str):
        self.seen_tokens.append((access_token, refresh_token))
        return self.returned_user


def test_get_user_from_token_requires_both_cookies():
    with pytest.raises(NotAuthorized):
        asyncio.run(
            user_from_token_route.getUserFromToken(
                access_token="access-token",
                refresh_token=None,
                auth=UserFromTokenAuth(returned_user=None),
            ),
        )


def test_get_user_from_token_forwards_cookie_tokens_to_auth_service(user_model):
    auth = UserFromTokenAuth(returned_user=user_model)

    result = asyncio.run(
        user_from_token_route.getUserFromToken(
            access_token="access-token",
            refresh_token="refresh-token",
            auth=auth,
        ),
    )

    assert result == user_model
    assert auth.seen_tokens == [("access-token", "refresh-token")]
