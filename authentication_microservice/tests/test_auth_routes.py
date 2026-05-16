import asyncio

import pytest

from app.api.version1.getUserFromToken import getUserFromToken
from app.api.version1.refresh import refresh
from app.errorsHandler.loginError import NotAuthorized
from app.errorsHandler.tokenError import CredentialException
from app.models.tokenModel import RefreshRequest, Token


def test_refresh_prefers_httponly_cookie_over_body_token():
    tokens_seen: list[str] = []

    class FakeAuth:
        def generateAccessTokenFromRefreshToken(self, refresh_token: str) -> Token:
            tokens_seen.append(refresh_token)
            return Token(accessToken="new-access-token", tokenType="ACCESS_TOKEN")

    result = asyncio.run(
        refresh(
            auth=FakeAuth(),
            refresh_token_cookie="cookie-refresh-token",
            body=RefreshRequest(refresh_token="body-refresh-token"),
        ),
    )

    assert result == Token(accessToken="new-access-token", tokenType="ACCESS_TOKEN")
    assert tokens_seen == ["cookie-refresh-token"]


def test_refresh_accepts_body_token_when_cookie_missing():
    tokens_seen: list[str] = []

    class FakeAuth:
        def generateAccessTokenFromRefreshToken(self, refresh_token: str) -> Token:
            tokens_seen.append(refresh_token)
            return Token(accessToken="new-access-token", tokenType="ACCESS_TOKEN")

    result = asyncio.run(
        refresh(
            auth=FakeAuth(),
            refresh_token_cookie=None,
            body=RefreshRequest(refresh_token="body-refresh-token"),
        ),
    )

    assert result.accessToken == "new-access-token"
    assert tokens_seen == ["body-refresh-token"]


def test_refresh_rejects_missing_refresh_token():
    class FakeAuth:
        def generateAccessTokenFromRefreshToken(self, refresh_token: str) -> Token:
            raise AssertionError("auth service should not be called")

    with pytest.raises(CredentialException, match="No Refresh Token provided"):
        asyncio.run(refresh(auth=FakeAuth(), refresh_token_cookie=None, body=None))


def test_get_user_from_token_requires_both_cookies():
    class FakeAuth:
        async def getUserFromAccessToken(self, access_token: str, refresh_token: str):
            raise AssertionError("auth service should not be called")

    with pytest.raises(NotAuthorized, match="No Access Token"):
        asyncio.run(
            getUserFromToken(
                access_token=None,
                refresh_token="refresh-token",
                auth=FakeAuth(),
            ),
        )

    with pytest.raises(NotAuthorized, match="No Refresh Token"):
        asyncio.run(
            getUserFromToken(
                access_token="access-token",
                refresh_token=None,
                auth=FakeAuth(),
            ),
        )


def test_get_user_from_token_uses_cookie_tokens(sample_user):
    tokens_seen: list[tuple[str, str]] = []

    class FakeAuth:
        async def getUserFromAccessToken(self, access_token: str, refresh_token: str):
            tokens_seen.append((access_token, refresh_token))
            return sample_user

    result = asyncio.run(
        getUserFromToken(
            access_token="access-token",
            refresh_token="refresh-token",
            auth=FakeAuth(),
        ),
    )

    assert result == sample_user
    assert tokens_seen == [("access-token", "refresh-token")]
