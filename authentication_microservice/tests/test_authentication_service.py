import asyncio
from datetime import timedelta

import jwt
import pytest

from app.errorsHandler.loginError import NotAuthorized
from app.errorsHandler.tokenError import CredentialException
from app.models.tokenModel import TokenModel
from app.services.authenticationService import AuthenticationService
from configurations.config import config


@pytest.fixture
def auth_service():
    return AuthenticationService(db=object())


def test_refresh_token_generates_access_token_with_same_identity(auth_service):
    refresh_token = auth_service._encodeRefreshToken(
        TokenModel(sub="user-123", email="user@example.com"),
        timedelta(days=1),
    )

    access_token = auth_service.generateAccessTokenFromRefreshToken(refresh_token)

    assert access_token.tokenType == "ACCESS_TOKEN"
    payload = jwt.decode(
        access_token.accessToken,
        config.AUTHENTICATION_SECRET_KEY,
        algorithms=[config.AUTHENTICATION_ALGORITHM],
    )
    assert payload["sub"] == "user-123"
    assert payload["email"] == "user@example.com"


def test_expired_refresh_token_is_not_exchanged(auth_service):
    refresh_token = auth_service._encodeRefreshToken(
        TokenModel(sub="user-123", email="user@example.com"),
        timedelta(seconds=-1),
    )

    with pytest.raises(NotAuthorized, match="Refresh token expired"):
        auth_service.generateAccessTokenFromRefreshToken(refresh_token)


def test_refresh_token_missing_subject_is_rejected(auth_service):
    refresh_token = jwt.encode(
        {"email": "user@example.com"},
        config.AUTHENTICATION_REFRESH_SECRET_KEY,
        algorithm=config.AUTHENTICATION_ALGORITHM,
    )

    with pytest.raises(CredentialException):
        auth_service.generateAccessTokenFromRefreshToken(refresh_token)


def test_expired_access_token_uses_refresh_then_retries(auth_service, monkeypatch):
    expired_access_token = auth_service._encodeAccessToken(
        TokenModel(sub="user-123", email="user@example.com"),
        timedelta(seconds=-1),
    )
    refresh_token = auth_service._encodeRefreshToken(
        TokenModel(sub="user-123", email="user@example.com"),
        timedelta(days=1),
    )
    expected_user = object()

    async def fake_decode_access_token(token: str):
        payload = jwt.decode(
            token,
            config.AUTHENTICATION_SECRET_KEY,
            algorithms=[config.AUTHENTICATION_ALGORITHM],
        )
        assert payload["sub"] == "user-123"
        assert payload["email"] == "user@example.com"
        return expected_user

    monkeypatch.setattr(auth_service, "decodeAccessToken", fake_decode_access_token)

    user = asyncio.run(
        auth_service.getUserFromAccessToken(expired_access_token, refresh_token),
    )

    assert user is expected_user


def test_invalid_access_token_does_not_attempt_refresh(auth_service, monkeypatch):
    invalid_access_token = jwt.encode(
        {"sub": "user-123", "email": "user@example.com"},
        "wrong-secret",
        algorithm=config.AUTHENTICATION_ALGORITHM,
    )

    def fail_if_refreshed(_refresh_token: str):
        raise AssertionError("invalid access tokens must not trigger refresh")

    monkeypatch.setattr(
        auth_service,
        "generateAccessTokenFromRefreshToken",
        fail_if_refreshed,
    )

    with pytest.raises(CredentialException):
        asyncio.run(
            auth_service.getUserFromAccessToken(invalid_access_token, "refresh-token"),
        )
