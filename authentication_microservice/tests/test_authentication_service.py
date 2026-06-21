import asyncio
from datetime import timedelta

import jwt
import pytest

from app.errorsHandler.loginError import NotAuthorized
from app.errorsHandler.tokenError import CredentialException
from app.services import authenticationService as auth_module


def test_refresh_generation_requires_real_refresh_token(authService, tokenPayload):
    access_token = authService._encodeAccessToken(tokenPayload, timedelta(minutes=5))

    with pytest.raises(CredentialException, match="Refresh token is required"):
        authService.generateAccessTokenFromRefreshToken("")

    with pytest.raises(CredentialException):
        authService.generateAccessTokenFromRefreshToken(access_token)


def test_refresh_generation_rejects_expired_refresh_token(authService, tokenPayload):
    expired_refresh = authService._encodeRefreshToken(tokenPayload, timedelta(seconds=-1))

    with pytest.raises(NotAuthorized, match="Refresh token expired"):
        authService.generateAccessTokenFromRefreshToken(expired_refresh)


def test_expired_access_token_uses_refresh_token_and_loads_user(
    authService,
    tokenPayload,
    userModel,
    monkeypatch,
):
    user_ids_seen: list[str] = []

    class FakeUserService:
        def __init__(self, db):
            self.db = db

        async def getUserFromUserId(self, user_id: str):
            user_ids_seen.append(user_id)
            return userModel

    monkeypatch.setattr(auth_module, "UserService", FakeUserService)

    expired_access = authService._encodeAccessToken(tokenPayload, timedelta(seconds=-1))
    refresh_token = authService._encodeRefreshToken(tokenPayload, timedelta(days=1))

    result = asyncio.run(
        authService.getUserFromAccessToken(expired_access, refresh_token)
    )

    assert result == userModel
    assert user_ids_seen == ["user-123"]


def test_malformed_access_token_does_not_refresh_or_query_user(
    authService,
    tokenPayload,
    monkeypatch,
):
    refresh_token = authService._encodeRefreshToken(tokenPayload, timedelta(days=1))
    refresh_attempted = False

    class FakeUserService:
        def __init__(self, db):
            self.db = db

        async def getUserFromUserId(self, user_id: str):
            raise AssertionError("malformed access tokens must not query users")

    def fail_if_refreshed(refresh_token: str):
        nonlocal refresh_attempted
        refresh_attempted = True
        raise AssertionError("malformed access tokens must not trigger refresh")

    monkeypatch.setattr(auth_module, "UserService", FakeUserService)
    monkeypatch.setattr(
        authService,
        "generateAccessTokenFromRefreshToken",
        fail_if_refreshed,
    )

    with pytest.raises(CredentialException):
        asyncio.run(authService.getUserFromAccessToken("not-a-jwt", refresh_token))

    assert refresh_attempted is False


def test_refresh_token_without_subject_is_rejected(authService):
    from configurations.config import config

    refresh_token = jwt.encode(
        {"email": "user@example.com"},
        config.AUTHENTICATION_REFRESH_SECRET_KEY,
        algorithm=config.AUTHENTICATION_ALGORITHM,
    )

    with pytest.raises(CredentialException):
        authService.generateAccessTokenFromRefreshToken(refresh_token)
