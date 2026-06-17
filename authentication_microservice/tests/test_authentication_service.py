import asyncio
from datetime import UTC, datetime, timedelta

import jwt
import pytest

from app.errorsHandler.loginError import NotAuthorized
from app.errorsHandler.tokenError import CredentialException
from app.models.tokenModel import TokenModel
from app.services.authenticationService import AuthenticationService
from configurations.config import config


def _token_model() -> TokenModel:
    return TokenModel(sub="user-123", email="user@example.com")


def test_refresh_token_generates_access_token_signed_with_access_secret():
    auth = AuthenticationService(db=object())
    refresh_token = auth._encodeRefreshToken(_token_model(), timedelta(minutes=5))

    access_token = auth.generateAccessTokenFromRefreshToken(refresh_token)

    assert access_token.tokenType == "ACCESS_TOKEN"
    decoded = jwt.decode(
        access_token.accessToken,
        config.AUTHENTICATION_SECRET_KEY,
        algorithms=[config.AUTHENTICATION_ALGORITHM],
    )
    assert decoded["sub"] == "user-123"
    assert decoded["email"] == "user@example.com"


def test_refresh_rejects_access_token_signed_with_wrong_secret():
    auth = AuthenticationService(db=object())
    access_token = auth._encodeAccessToken(_token_model(), timedelta(minutes=5))

    with pytest.raises(CredentialException):
        auth.generateAccessTokenFromRefreshToken(access_token)


def test_refresh_rejects_expired_refresh_token():
    auth = AuthenticationService(db=object())
    expired_refresh = auth._encodeRefreshToken(_token_model(), timedelta(seconds=-1))

    with pytest.raises(NotAuthorized, match="Refresh token expired"):
        auth.generateAccessTokenFromRefreshToken(expired_refresh)


def test_refresh_rejects_token_without_subject():
    auth = AuthenticationService(db=object())
    refresh_without_sub = jwt.encode(
        {
            "email": "user@example.com",
            "exp": datetime.now(UTC) + timedelta(minutes=5),
        },
        config.AUTHENTICATION_REFRESH_SECRET_KEY,
        algorithm=config.AUTHENTICATION_ALGORITHM,
    )

    with pytest.raises(CredentialException):
        auth.generateAccessTokenFromRefreshToken(refresh_without_sub)


def test_expired_access_token_uses_refresh_token_to_load_user(monkeypatch, user_model):
    from app.services import authenticationService as authentication_module

    seen_user_ids: list[str] = []

    class FakeUserService:
        def __init__(self, db):
            self.db = db

        async def getUserFromUserId(self, user_id: str):
            seen_user_ids.append(user_id)
            return user_model

    monkeypatch.setattr(authentication_module, "UserService", FakeUserService)
    auth = AuthenticationService(db=object())
    expired_access = auth._encodeAccessToken(_token_model(), timedelta(seconds=-1))
    refresh_token = auth._encodeRefreshToken(_token_model(), timedelta(minutes=5))

    result = asyncio.run(auth.getUserFromAccessToken(expired_access, refresh_token))

    assert result == user_model
    assert seen_user_ids == ["user-123"]


def test_invalid_access_token_does_not_attempt_refresh(monkeypatch):
    auth = AuthenticationService(db=object())
    refresh_attempted = False

    def fail_if_refreshed(refresh_token: str):
        nonlocal refresh_attempted
        refresh_attempted = True
        raise AssertionError("Invalid access tokens must not be refreshed")

    monkeypatch.setattr(auth, "generateAccessTokenFromRefreshToken", fail_if_refreshed)

    with pytest.raises(CredentialException):
        asyncio.run(auth.getUserFromAccessToken("not-a-jwt", "refresh-token"))

    assert refresh_attempted is False
