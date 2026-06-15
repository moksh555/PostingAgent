import asyncio
from datetime import UTC, datetime, timedelta

import jwt  # type: ignore
import pytest

from app.errorsHandler.tokenError import CredentialException
from app.models.tokenModel import TokenModel
from app.models.userModel import UserModel
from app.services import authenticationService as auth_module
from app.services.authenticationService import AuthenticationService
from configurations.config import config


class FakeUserService:
    calls: list[str] = []

    def __init__(self, _db):
        pass

    async def getUserFromUserId(self, user_id: str) -> UserModel:
        self.calls.append(user_id)
        return UserModel(
            email="user@example.com",
            sub=user_id,
            userFirstName="test",
            userLastName="user",
            phoneNumber="12345678",
            dateOfBirth=datetime(1990, 1, 1, tzinfo=UTC),
            createdAt=datetime(2026, 1, 1, tzinfo=UTC),
            isActive=True,
            subscriptionType="free",
        )


@pytest.fixture
def auth_service():
    return AuthenticationService(db=object())


def test_access_and_refresh_tokens_use_separate_signing_keys(auth_service):
    token_data = TokenModel(sub="user-1", email="user@example.com")

    access_token = auth_service._encodeAccessToken(token_data, timedelta(minutes=5))
    refresh_token = auth_service._encodeRefreshToken(token_data, timedelta(days=5))

    access_payload = jwt.decode(
        access_token,
        config.AUTHENTICATION_SECRET_KEY,
        algorithms=[config.AUTHENTICATION_ALGORITHM],
    )
    refresh_payload = jwt.decode(
        refresh_token,
        config.AUTHENTICATION_REFRESH_SECRET_KEY,
        algorithms=[config.AUTHENTICATION_ALGORITHM],
    )

    assert access_payload["sub"] == "user-1"
    assert refresh_payload["sub"] == "user-1"
    with pytest.raises(jwt.InvalidTokenError):
        jwt.decode(
            refresh_token,
            config.AUTHENTICATION_SECRET_KEY,
            algorithms=[config.AUTHENTICATION_ALGORITHM],
        )


def test_generate_access_token_from_refresh_preserves_identity(auth_service):
    refresh_token = auth_service._encodeRefreshToken(
        TokenModel(sub="user-2", email="user@example.com"),
        timedelta(days=1),
    )

    result = auth_service.generateAccessTokenFromRefreshToken(refresh_token)

    assert result.tokenType == "ACCESS_TOKEN"
    payload = jwt.decode(
        result.accessToken,
        config.AUTHENTICATION_SECRET_KEY,
        algorithms=[config.AUTHENTICATION_ALGORITHM],
    )
    assert payload["sub"] == "user-2"
    assert payload["email"] == "user@example.com"


def test_refresh_rejects_token_signed_with_access_secret(auth_service):
    access_token = auth_service._encodeAccessToken(
        TokenModel(sub="user-3", email="user@example.com"),
        timedelta(minutes=5),
    )

    with pytest.raises(CredentialException):
        auth_service.generateAccessTokenFromRefreshToken(access_token)


def test_expired_access_token_uses_refresh_token_to_load_user(auth_service, monkeypatch):
    FakeUserService.calls = []
    monkeypatch.setattr(auth_module, "UserService", FakeUserService)
    expired_access = auth_service._encodeAccessToken(
        TokenModel(sub="user-4", email="user@example.com"),
        timedelta(minutes=-1),
    )
    refresh_token = auth_service._encodeRefreshToken(
        TokenModel(sub="user-4", email="user@example.com"),
        timedelta(days=1),
    )

    user = asyncio.run(
        auth_service.getUserFromAccessToken(expired_access, refresh_token)
    )

    assert user.sub == "user-4"
    assert FakeUserService.calls == ["user-4"]


def test_invalid_access_token_does_not_attempt_refresh(auth_service, monkeypatch):
    def fail_if_called(_refresh_token: str):
        raise AssertionError("refresh should only happen for expired access tokens")

    monkeypatch.setattr(
        auth_service,
        "generateAccessTokenFromRefreshToken",
        fail_if_called,
    )

    with pytest.raises(CredentialException):
        asyncio.run(auth_service.getUserFromAccessToken("not-a-jwt", "refresh"))
