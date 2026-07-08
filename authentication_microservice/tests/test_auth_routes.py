import asyncio
from datetime import datetime, timezone

import pytest
from fastapi import Response

from app.api.version1 import getUserFromToken as get_user_from_token_module
from app.api.version1 import login as login_module
from app.api.version1 import refresh as refresh_module
from app.api.version1 import register as register_module
from app.errorsHandler.loginError import NotAuthorized
from app.errorsHandler.tokenError import CredentialException
from app.models.loginModel import LoginRequest
from app.models.registerModel import RegisterRequest
from app.models.tokenModel import RefreshRequest, Token
from app.models.userModel import UserModel


def _set_cookie_headers(response: Response) -> list[str]:
    return [
        value.decode("latin-1")
        for name, value in response.raw_headers
        if name == b"set-cookie"
    ]


def _assert_auth_cookie_pair(response: Response) -> None:
    headers = _set_cookie_headers(response)

    assert any(
        header.startswith("refresh_token=refresh-token;")
        and "HttpOnly" in header
        and "Secure" in header
        and "Max-Age=432000" in header
        for header in headers
    )
    assert any(
        header.startswith("access_token=access-token;")
        and "HttpOnly" in header
        and "Secure" in header
        and "Max-Age=1800" in header
        for header in headers
    )


class FakeAuth:
    def __init__(self) -> None:
        self.refresh_tokens_seen: list[str] = []
        self.user_token_pairs_seen: list[tuple[str, str]] = []

    def generateAccessTokenFromRefreshToken(self, refresh_token: str) -> Token:
        self.refresh_tokens_seen.append(refresh_token)
        return Token(accessToken="new-access-token", tokenType="ACCESS_TOKEN")

    async def loginUser(self, request: LoginRequest) -> tuple[Token, Token]:
        return (
            Token(accessToken="access-token", tokenType="ACCESS_TOKEN"),
            Token(accessToken="refresh-token", tokenType="REFRESH_TOKEN"),
        )

    async def registerUser(self, request: RegisterRequest) -> tuple[Token, Token]:
        return (
            Token(accessToken="access-token", tokenType="ACCESS_TOKEN"),
            Token(accessToken="refresh-token", tokenType="REFRESH_TOKEN"),
        )

    async def getUserFromAccessToken(
        self,
        access_token: str,
        refresh_token: str,
    ) -> UserModel:
        self.user_token_pairs_seen.append((access_token, refresh_token))
        return UserModel(
            email="user@example.com",
            sub="user-123",
            userFirstName="test",
            userLastName="user",
            phoneNumber="+15555550123",
            dateOfBirth=datetime(1990, 1, 1, tzinfo=timezone.utc),
            createdAt=datetime(2024, 1, 1, tzinfo=timezone.utc),
            isActive=True,
            subscriptionType="free",
        )


def test_refresh_prefers_cookie_over_body_token() -> None:
    auth = FakeAuth()

    response = asyncio.run(
        refresh_module.refresh(
            auth=auth,
            refresh_token_cookie="cookie-token",
            body=RefreshRequest(refresh_token="body-token"),
        ),
    )

    assert response == Token(accessToken="new-access-token", tokenType="ACCESS_TOKEN")
    assert auth.refresh_tokens_seen == ["cookie-token"]


def test_refresh_rejects_missing_refresh_token() -> None:
    with pytest.raises(CredentialException, match="No Refresh Token provided"):
        asyncio.run(
            refresh_module.refresh(
                auth=FakeAuth(),
                refresh_token_cookie=None,
                body=None,
            ),
        )


@pytest.mark.parametrize(
    "route_call",
    [
        lambda auth, response: login_module.login(
            LoginRequest(email="user@example.com", password="StrongPass1!"),
            response,
            auth=auth,
        ),
        lambda auth, response: register_module.register(
            RegisterRequest(
                email="user@example.com",
                password="StrongPass1!",
                dateOfBirth=datetime(1990, 1, 1, tzinfo=timezone.utc),
                firstName="Test",
                lastName="User",
                phoneNumber="+15555550123",
            ),
            response,
            auth=auth,
        ),
    ],
)
def test_login_and_register_set_secure_http_only_token_cookies(route_call) -> None:
    response = Response()

    result = asyncio.run(route_call(FakeAuth(), response))

    assert result.status == "success"
    _assert_auth_cookie_pair(response)


@pytest.mark.parametrize(
    ("access_token", "refresh_token", "message"),
    [
        (None, "refresh-token", "No Access Token provided"),
        ("access-token", None, "No Refresh Token provided"),
    ],
)
def test_get_user_from_token_requires_access_and_refresh_cookies(
    access_token: str | None,
    refresh_token: str | None,
    message: str,
) -> None:
    with pytest.raises(NotAuthorized, match=message):
        asyncio.run(
            get_user_from_token_module.getUserFromToken(
                access_token=access_token,
                refresh_token=refresh_token,
                auth=FakeAuth(),
            ),
        )


def test_get_user_from_token_forwards_cookie_pair_to_auth_service() -> None:
    auth = FakeAuth()

    user = asyncio.run(
        get_user_from_token_module.getUserFromToken(
            access_token="access-token",
            refresh_token="refresh-token",
            auth=auth,
        ),
    )

    assert user.sub == "user-123"
    assert auth.user_token_pairs_seen == [("access-token", "refresh-token")]
