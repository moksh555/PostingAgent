import asyncio
from datetime import UTC, datetime

import pytest
from fastapi import Response  # type: ignore

from app.api.version1 import getUserFromToken as get_user_route
from app.api.version1 import login as login_route
from app.api.version1 import refresh as refresh_route
from app.api.version1 import register as register_route
from app.errorsHandler.loginError import NotAuthorized
from app.errorsHandler.tokenError import CredentialException
from app.models.loginModel import LoginRequest
from app.models.registerModel import RegisterRequest
from app.models.tokenModel import RefreshRequest, Token


class FakeCookieAuthService:
    def __init__(self):
        self.login_requests = []
        self.register_requests = []

    async def loginUser(self, request):
        self.login_requests.append(request)
        return (
            Token(accessToken="access-token", tokenType="ACCESS_TOKEN"),
            Token(accessToken="refresh-token", tokenType="REFRESH_TOKEN"),
        )

    async def registerUser(self, request):
        self.register_requests.append(request)
        return (
            Token(accessToken="access-token", tokenType="ACCESS_TOKEN"),
            Token(accessToken="refresh-token", tokenType="REFRESH_TOKEN"),
        )


class FakeRefreshAuthService:
    def __init__(self):
        self.refresh_tokens = []

    def generateAccessTokenFromRefreshToken(self, refresh_token: str):
        self.refresh_tokens.append(refresh_token)
        return Token(accessToken=f"access-for-{refresh_token}", tokenType="ACCESS_TOKEN")


class FakeUserFromTokenAuthService:
    def __init__(self, user):
        self.user = user
        self.calls = []

    async def getUserFromAccessToken(self, access_token: str, refresh_token: str):
        self.calls.append((access_token, refresh_token))
        return self.user


def _set_cookie_headers(response: Response) -> list[str]:
    return [
        value.decode("latin-1")
        for key, value in response.raw_headers
        if key.lower() == b"set-cookie"
    ]


@pytest.mark.parametrize(
    ("handler", "request_obj", "auth_call_attr", "success_message"),
    [
        (
            login_route.login,
            LoginRequest(email="user@example.com", password="CorrectHorse1!"),
            "login_requests",
            "Login successful",
        ),
        (
            register_route.register,
            RegisterRequest(
                email="user@example.com",
                password="CorrectHorse1!",
                dateOfBirth=datetime(1990, 1, 1, tzinfo=UTC),
                firstName="Ada",
                lastName="Lovelace",
                phoneNumber="+15555550123",
            ),
            "register_requests",
            "Register successful",
        ),
    ],
)
def test_login_and_register_set_secure_http_only_token_cookies(
    handler,
    request_obj,
    auth_call_attr,
    success_message,
):
    response = Response()
    auth = FakeCookieAuthService()

    result = asyncio.run(handler(request_obj, response, auth))

    assert result.message == success_message
    assert result.status == "success"
    assert getattr(auth, auth_call_attr) == [request_obj]

    cookie_headers = _set_cookie_headers(response)
    assert len(cookie_headers) == 2
    refresh_cookie = next(header for header in cookie_headers if "refresh_token=" in header)
    access_cookie = next(header for header in cookie_headers if "access_token=" in header)

    assert "refresh_token=refresh-token" in refresh_cookie
    assert "Max-Age=432000" in refresh_cookie
    assert "HttpOnly" in refresh_cookie
    assert "Secure" in refresh_cookie

    assert "access_token=access-token" in access_cookie
    assert "Max-Age=1800" in access_cookie
    assert "HttpOnly" in access_cookie
    assert "Secure" in access_cookie


def test_refresh_prefers_cookie_over_json_body():
    auth = FakeRefreshAuthService()

    token = asyncio.run(
        refresh_route.refresh(
            auth=auth,
            refresh_token_cookie="cookie-refresh",
            body=RefreshRequest(refresh_token="body-refresh"),
        ),
    )

    assert token == Token(accessToken="access-for-cookie-refresh", tokenType="ACCESS_TOKEN")
    assert auth.refresh_tokens == ["cookie-refresh"]


def test_refresh_uses_json_body_when_cookie_missing():
    auth = FakeRefreshAuthService()

    token = asyncio.run(
        refresh_route.refresh(
            auth=auth,
            refresh_token_cookie=None,
            body=RefreshRequest(refresh_token="body-refresh"),
        ),
    )

    assert token == Token(accessToken="access-for-body-refresh", tokenType="ACCESS_TOKEN")
    assert auth.refresh_tokens == ["body-refresh"]


def test_refresh_requires_a_cookie_or_body_token():
    with pytest.raises(CredentialException, match="No Refresh Token provided"):
        asyncio.run(
            refresh_route.refresh(
                auth=FakeRefreshAuthService(),
                refresh_token_cookie=None,
                body=None,
            ),
        )


def test_get_user_from_token_requires_access_and_refresh_cookies(sample_user):
    auth = FakeUserFromTokenAuthService(sample_user)

    user = asyncio.run(
        get_user_route.getUserFromToken(
            access_token="access-cookie",
            refresh_token="refresh-cookie",
            auth=auth,
        ),
    )

    assert user == sample_user
    assert auth.calls == [("access-cookie", "refresh-cookie")]


@pytest.mark.parametrize(
    ("access_token", "refresh_token", "expected_message"),
    [
        (None, "refresh-cookie", "No Access Token provided"),
        ("access-cookie", None, "No Refresh Token provided"),
    ],
)
def test_get_user_from_token_rejects_missing_cookies(
    access_token,
    refresh_token,
    expected_message,
    sample_user,
):
    auth = FakeUserFromTokenAuthService(sample_user)

    with pytest.raises(NotAuthorized, match=expected_message):
        asyncio.run(
            get_user_route.getUserFromToken(
                access_token=access_token,
                refresh_token=refresh_token,
                auth=auth,
            ),
        )

    assert auth.calls == []
