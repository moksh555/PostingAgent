import asyncio
from datetime import UTC, datetime, timedelta

import jwt  # type: ignore
import pytest

from app.errorsHandler.loginError import NotAuthorized
from app.errorsHandler.tokenError import CredentialException
from app.models.tokenModel import TokenModel
from app.services import authenticationService as auth_module
from configurations.config import config


class FakeUserService:
    def __init__(self, user):
        self.user = user
        self.lookups: list[str] = []

    async def getUserFromUserId(self, user_id: str):
        self.lookups.append(user_id)
        return self.user


def test_refresh_exchange_requires_refresh_signing_key():
    service = auth_module.AuthenticationService(db=object())
    token_data = TokenModel(sub="user-123", email="user@example.com")

    access_token = service._encodeAccessToken(token_data, timedelta(minutes=5))
    with pytest.raises(CredentialException):
        service.generateAccessTokenFromRefreshToken(access_token)

    refresh_token = service._encodeRefreshToken(token_data, timedelta(days=1))
    new_access = service.generateAccessTokenFromRefreshToken(refresh_token)

    assert new_access.tokenType == "ACCESS_TOKEN"
    payload = jwt.decode(
        new_access.accessToken,
        config.AUTHENTICATION_SECRET_KEY,
        algorithms=[config.AUTHENTICATION_ALGORITHM],
    )
    assert payload["sub"] == "user-123"
    assert payload["email"] == "user@example.com"


def test_refresh_exchange_rejects_tokens_without_subject():
    service = auth_module.AuthenticationService(db=object())
    refresh_token = jwt.encode(
        {
            "email": "user@example.com",
            "exp": datetime.now(UTC) + timedelta(days=1),
        },
        config.AUTHENTICATION_REFRESH_SECRET_KEY,
        algorithm=config.AUTHENTICATION_ALGORITHM,
    )

    with pytest.raises(CredentialException):
        service.generateAccessTokenFromRefreshToken(refresh_token)


def test_refresh_exchange_rejects_expired_refresh_tokens():
    service = auth_module.AuthenticationService(db=object())
    refresh_token = jwt.encode(
        {
            "sub": "user-123",
            "email": "user@example.com",
            "exp": datetime.now(UTC) - timedelta(seconds=1),
        },
        config.AUTHENTICATION_REFRESH_SECRET_KEY,
        algorithm=config.AUTHENTICATION_ALGORITHM,
    )

    with pytest.raises(NotAuthorized, match="Refresh token expired"):
        service.generateAccessTokenFromRefreshToken(refresh_token)


def test_expired_access_token_uses_refresh_token_and_retries_lookup(
    sample_user,
    monkeypatch,
):
    fake_users = FakeUserService(sample_user)
    monkeypatch.setattr(auth_module, "UserService", lambda db: fake_users)
    service = auth_module.AuthenticationService(db=object())
    token_data = TokenModel(sub=sample_user.sub, email=sample_user.email)
    expired_access = service._encodeAccessToken(token_data, -timedelta(seconds=1))
    refresh_token = service._encodeRefreshToken(token_data, timedelta(days=1))

    result = asyncio.run(
        service.getUserFromAccessToken(expired_access, refresh_token),
    )

    assert result == sample_user
    assert fake_users.lookups == [sample_user.sub]


def test_invalid_access_token_does_not_attempt_refresh(sample_user, monkeypatch):
    fake_users = FakeUserService(sample_user)
    monkeypatch.setattr(auth_module, "UserService", lambda db: fake_users)
    service = auth_module.AuthenticationService(db=object())

    def fail_refresh(_refresh_token: str):
        raise AssertionError("invalid access tokens must not trigger refresh")

    monkeypatch.setattr(service, "generateAccessTokenFromRefreshToken", fail_refresh)

    with pytest.raises(CredentialException):
        asyncio.run(
            service.getUserFromAccessToken(
                "not-a-jwt",
                "refresh-token-that-should-not-be-used",
            )
        )
    assert fake_users.lookups == []
