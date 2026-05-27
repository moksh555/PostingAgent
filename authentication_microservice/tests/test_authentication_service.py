import asyncio
from datetime import timedelta

import jwt
import pytest

from app.errorsHandler.loginError import NotAuthorized
from app.errorsHandler.tokenError import CredentialException
from app.models.tokenModel import TokenModel
from app.services.authenticationService import AuthenticationService
from configurations.config import config


def test_generate_access_token_from_refresh_token_preserves_identity_claims():
    service = AuthenticationService(db=object())
    refresh_token = service._encodeRefreshToken(
        TokenModel(sub="user-123", email="user@example.com"),
        timedelta(minutes=5),
    )

    access_token = service.generateAccessTokenFromRefreshToken(refresh_token)

    payload = jwt.decode(
        access_token.accessToken,
        config.AUTHENTICATION_SECRET_KEY,
        algorithms=[config.AUTHENTICATION_ALGORITHM],
    )
    assert access_token.tokenType == "ACCESS_TOKEN"
    assert payload["sub"] == "user-123"
    assert payload["email"] == "user@example.com"


def test_generate_access_token_from_refresh_token_rejects_expired_refresh_token():
    service = AuthenticationService(db=object())
    refresh_token = service._encodeRefreshToken(
        TokenModel(sub="user-123", email="user@example.com"),
        timedelta(seconds=-1),
    )

    with pytest.raises(NotAuthorized, match="Refresh token expired"):
        service.generateAccessTokenFromRefreshToken(refresh_token)


def test_generate_access_token_from_refresh_token_rejects_missing_subject_claim():
    service = AuthenticationService(db=object())
    refresh_token = jwt.encode(
        {"email": "user@example.com"},
        config.AUTHENTICATION_REFRESH_SECRET_KEY,
        algorithm=config.AUTHENTICATION_ALGORITHM,
    )

    with pytest.raises(CredentialException):
        service.generateAccessTokenFromRefreshToken(refresh_token)


def test_expired_access_token_refreshes_once_and_uses_new_access_token(
    monkeypatch,
    sample_user,
):
    service = AuthenticationService(db=object())
    expired_access = service._encodeAccessToken(
        TokenModel(sub="user-123", email="user@example.com"),
        timedelta(seconds=-1),
    )
    refresh_token = service._encodeRefreshToken(
        TokenModel(sub="user-123", email="user@example.com"),
        timedelta(minutes=5),
    )
    decoded_access_tokens: list[str] = []

    async def fake_decode_access_token(access_token: str):
        decoded_access_tokens.append(access_token)
        return sample_user

    monkeypatch.setattr(service, "decodeAccessToken", fake_decode_access_token)

    user = asyncio.run(
        service.getUserFromAccessToken(
            accessToken=expired_access,
            refreshToken=refresh_token,
        )
    )

    assert user == sample_user
    assert len(decoded_access_tokens) == 1
    refreshed_payload = jwt.decode(
        decoded_access_tokens[0],
        config.AUTHENTICATION_SECRET_KEY,
        algorithms=[config.AUTHENTICATION_ALGORITHM],
    )
    assert refreshed_payload["sub"] == "user-123"


def test_invalid_access_token_does_not_attempt_refresh(monkeypatch):
    service = AuthenticationService(db=object())

    def fail_if_refresh_is_attempted(refresh_token: str):
        raise AssertionError("invalid access tokens must not trigger refresh")

    monkeypatch.setattr(
        service,
        "generateAccessTokenFromRefreshToken",
        fail_if_refresh_is_attempted,
    )

    with pytest.raises(CredentialException):
        asyncio.run(
            service.getUserFromAccessToken(
                accessToken="not-a-jwt",
                refreshToken="unused-refresh-token",
            )
        )
