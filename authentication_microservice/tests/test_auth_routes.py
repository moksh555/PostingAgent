import asyncio

import pytest
from fastapi import Response

from app.api.version1.getUserFromToken import getUserFromToken
from app.api.version1.login import login
from app.api.version1.refresh import refresh
from app.errorsHandler.loginError import NotAuthorized
from app.errorsHandler.tokenError import CredentialException
from app.models.loginModel import LoginRequest
from app.models.tokenModel import RefreshRequest, Token


def run(coro):
    return asyncio.run(coro)


def _set_cookie_headers(response: Response) -> list[str]:
    return [
        value.decode()
        for key, value in response.raw_headers
        if key == b"set-cookie"
    ]


class FakeLoginAuth:
    async def loginUser(self, _request: LoginRequest) -> tuple[Token, Token]:
        return (
            Token(accessToken="access.jwt", tokenType="ACCESS_TOKEN"),
            Token(accessToken="refresh.jwt", tokenType="REFRESH_TOKEN"),
        )


class FakeRefreshAuth:
    def __init__(self) -> None:
        self.refresh_token: str | None = None

    def generateAccessTokenFromRefreshToken(self, refresh_token: str) -> Token:
        self.refresh_token = refresh_token
        return Token(accessToken=f"new-{refresh_token}", tokenType="ACCESS_TOKEN")


class FailingTokenAuth:
    async def getUserFromAccessToken(self, _access_token: str, _refresh_token: str):
        raise AssertionError("auth service should not be called")


def test_login_sets_secure_httponly_access_and_refresh_cookies() -> None:
    response = Response()

    body = run(
        login(
            LoginRequest(email="USER@example.com", password="CorrectHorse1!"),
            response,
            FakeLoginAuth(),  # type: ignore[arg-type]
        )
    )

    cookies = _set_cookie_headers(response)
    assert body.message == "Login successful"
    assert body.status == "success"
    assert any(
        cookie.startswith("refresh_token=refresh.jwt;")
        and "HttpOnly" in cookie
        and "Secure" in cookie
        and "Max-Age=432000" in cookie
        for cookie in cookies
    )
    assert any(
        cookie.startswith("access_token=access.jwt;")
        and "HttpOnly" in cookie
        and "Secure" in cookie
        and "Max-Age=1800" in cookie
        for cookie in cookies
    )


def test_refresh_prefers_httponly_cookie_over_body_token() -> None:
    auth = FakeRefreshAuth()

    token = run(
        refresh(
            auth=auth,  # type: ignore[arg-type]
            refresh_token_cookie="cookie-token",
            body=RefreshRequest(refresh_token="body-token"),
        )
    )

    assert auth.refresh_token == "cookie-token"
    assert token.accessToken == "new-cookie-token"
    assert token.tokenType == "ACCESS_TOKEN"


def test_refresh_requires_cookie_or_body_token() -> None:
    with pytest.raises(CredentialException):
        run(
            refresh(
                auth=FakeRefreshAuth(),  # type: ignore[arg-type]
                refresh_token_cookie=None,
                body=RefreshRequest(refresh_token=None),
            )
        )


def test_get_user_from_token_requires_refresh_cookie_before_service_call() -> None:
    with pytest.raises(NotAuthorized) as exc_info:
        run(
            getUserFromToken(
                access_token="access.jwt",
                refresh_token=None,
                auth=FailingTokenAuth(),  # type: ignore[arg-type]
            )
        )

    assert "No Refresh Token provided" in exc_info.value.message
