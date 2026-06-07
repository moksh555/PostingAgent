import asyncio
from datetime import timedelta

import jwt
import pytest

from app.errorsHandler.tokenError import CredentialException
from app.models.tokenModel import TokenModel
from app.services import authenticationService as auth_module
from app.services.authenticationService import AuthenticationService
from configurations.config import config


class FakeUserService:
    calls: list[str] = []
    user = None

    def __init__(self, _db):
        pass

    async def getUserFromUserId(self, user_id: str):
        self.calls.append(user_id)
        return self.user


@pytest.fixture(autouse=True)
def reset_fake_user_service(sample_user):
    FakeUserService.calls = []
    FakeUserService.user = sample_user


@pytest.fixture
def auth_service(monkeypatch):
    monkeypatch.setattr(auth_module, "UserService", FakeUserService)
    return AuthenticationService(db=object())


def decode_access_token(token: str) -> dict:
    return jwt.decode(
        token,
        config.AUTHENTICATION_SECRET_KEY,
        algorithms=[config.AUTHENTICATION_ALGORITHM],
    )


def test_generate_access_token_from_valid_refresh_token(auth_service):
    refresh_token = auth_service._encodeRefreshToken(
        TokenModel(sub="user-123", email="user@example.com"),
        timedelta(days=1),
    )

    access_token = auth_service.generateAccessTokenFromRefreshToken(refresh_token)

    assert access_token.tokenType == "ACCESS_TOKEN"
    payload = decode_access_token(access_token.accessToken)
    assert payload["sub"] == "user-123"
    assert payload["email"] == "user@example.com"


def test_generate_access_token_rejects_access_token_signed_with_wrong_secret(auth_service):
    access_token = auth_service._encodeAccessToken(
        TokenModel(sub="user-123", email="user@example.com"),
        timedelta(minutes=5),
    )

    with pytest.raises(CredentialException):
        auth_service.generateAccessTokenFromRefreshToken(access_token)


def test_get_user_refreshes_only_when_access_token_is_expired(auth_service, sample_user):
    expired_access_token = auth_service._encodeAccessToken(
        TokenModel(sub="user-123", email="user@example.com"),
        timedelta(seconds=-1),
    )
    refresh_token = auth_service._encodeRefreshToken(
        TokenModel(sub="user-123", email="user@example.com"),
        timedelta(days=1),
    )

    user = asyncio.run(
        auth_service.getUserFromAccessToken(
            expired_access_token,
            refresh_token,
        )
    )

    assert user == sample_user
    assert FakeUserService.calls == ["user-123"]


def test_get_user_does_not_refresh_malformed_access_token(auth_service, monkeypatch):
    def fail_if_refresh_attempted(_refresh_token):
        raise AssertionError("invalid access token must not trigger refresh")

    monkeypatch.setattr(
        auth_service,
        "generateAccessTokenFromRefreshToken",
        fail_if_refresh_attempted,
    )

    with pytest.raises(CredentialException):
        asyncio.run(
            auth_service.getUserFromAccessToken(
                "not-a-jwt",
                "refresh-token",
            )
        )

    assert FakeUserService.calls == []
