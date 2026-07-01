import asyncio
from datetime import UTC, datetime, timedelta

import jwt  # type: ignore
import pytest

from app.errorsHandler.tokenError import CredentialException
from app.models.tokenModel import TokenModel
from app.services import authenticationService as auth_module
from configurations.config import config


def test_refresh_token_mints_access_token_with_access_secret(auth_service):
    data = TokenModel(sub="user-123", email="user@example.com")
    refresh_token = auth_service._encodeRefreshToken(data, timedelta(minutes=5))

    access = auth_service.generateAccessTokenFromRefreshToken(refresh_token)

    assert access.tokenType == "ACCESS_TOKEN"
    decoded = jwt.decode(
        access.accessToken,
        config.AUTHENTICATION_SECRET_KEY,
        algorithms=[config.AUTHENTICATION_ALGORITHM],
    )
    assert decoded["sub"] == "user-123"
    assert decoded["email"] == "user@example.com"

    with pytest.raises(jwt.InvalidTokenError):
        jwt.decode(
            access.accessToken,
            config.AUTHENTICATION_REFRESH_SECRET_KEY,
            algorithms=[config.AUTHENTICATION_ALGORITHM],
        )


def test_access_token_cannot_be_used_as_refresh_token(auth_service):
    data = TokenModel(sub="user-123", email="user@example.com")
    access_token = auth_service._encodeAccessToken(data, timedelta(minutes=5))

    with pytest.raises(CredentialException):
        auth_service.generateAccessTokenFromRefreshToken(access_token)


def test_refresh_token_without_subject_is_rejected(auth_service):
    refresh_token = jwt.encode(
        {
            "email": "user@example.com",
            "exp": datetime.now(UTC) + timedelta(minutes=5),
        },
        config.AUTHENTICATION_REFRESH_SECRET_KEY,
        algorithm=config.AUTHENTICATION_ALGORITHM,
    )

    with pytest.raises(CredentialException):
        auth_service.generateAccessTokenFromRefreshToken(refresh_token)


def test_expired_access_token_uses_refresh_token_and_retries_lookup(
    auth_service,
    sample_user,
    monkeypatch,
):
    user_ids: list[str] = []

    class FakeUserService:
        def __init__(self, _db):
            pass

        async def getUserFromUserId(self, user_id: str):
            user_ids.append(user_id)
            return sample_user

    monkeypatch.setattr(auth_module, "UserService", FakeUserService)
    data = TokenModel(sub=sample_user.sub, email=sample_user.email)
    expired_access = auth_service._encodeAccessToken(data, timedelta(seconds=-1))
    refresh_token = auth_service._encodeRefreshToken(data, timedelta(minutes=5))

    result = asyncio.run(
        auth_service.getUserFromAccessToken(expired_access, refresh_token)
    )

    assert result == sample_user
    assert user_ids == [sample_user.sub]


def test_invalid_access_token_does_not_attempt_refresh(auth_service, monkeypatch):
    def fail_refresh(_refresh_token: str):
        raise AssertionError("invalid access tokens must not be refreshed")

    class FailingUserService:
        def __init__(self, _db):
            pass

        async def getUserFromUserId(self, _user_id: str):
            raise AssertionError("invalid access tokens must not look up users")

    monkeypatch.setattr(auth_module, "UserService", FailingUserService)
    monkeypatch.setattr(auth_service, "generateAccessTokenFromRefreshToken", fail_refresh)

    with pytest.raises(CredentialException):
        asyncio.run(
            auth_service.getUserFromAccessToken("not-a-jwt", "unused-refresh")
        )
