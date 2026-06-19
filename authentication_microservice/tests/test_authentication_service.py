import asyncio
from datetime import timedelta

import jwt
import pytest

from app.errorsHandler.loginError import NotAuthorized
from app.errorsHandler.tokenError import CredentialException
from app.models.tokenModel import TokenModel
from configurations.config import config


def test_refresh_tokens_are_signed_with_refresh_secret(auth_service):
    token_data = TokenModel(sub="user-123", email="user@example.com")

    refresh_token = auth_service._encodeRefreshToken(token_data, timedelta(days=1))

    with pytest.raises(jwt.InvalidTokenError):
        jwt.decode(
            refresh_token,
            config.AUTHENTICATION_SECRET_KEY,
            algorithms=[config.AUTHENTICATION_ALGORITHM],
        )

    access_token = auth_service.generateAccessTokenFromRefreshToken(refresh_token)
    decoded_access = jwt.decode(
        access_token.accessToken,
        config.AUTHENTICATION_SECRET_KEY,
        algorithms=[config.AUTHENTICATION_ALGORITHM],
    )
    assert access_token.tokenType == "ACCESS_TOKEN"
    assert decoded_access["sub"] == "user-123"
    assert decoded_access["email"] == "user@example.com"


def test_refresh_rejects_access_token_signed_with_wrong_secret(auth_service):
    token_data = TokenModel(sub="user-123", email="user@example.com")
    access_token = auth_service._encodeAccessToken(token_data, timedelta(minutes=5))

    with pytest.raises(CredentialException):
        auth_service.generateAccessTokenFromRefreshToken(access_token)


def test_refresh_rejects_expired_refresh_token(auth_service):
    token_data = TokenModel(sub="user-123", email="user@example.com")
    expired_refresh = auth_service._encodeRefreshToken(
        token_data,
        timedelta(seconds=-1),
    )

    with pytest.raises(NotAuthorized, match="Refresh token expired"):
        auth_service.generateAccessTokenFromRefreshToken(expired_refresh)


def test_get_user_refreshes_only_when_access_token_is_expired(
    auth_service,
    monkeypatch,
    sample_user,
):
    requested_user_ids: list[str] = []

    class FakeUserService:
        def __init__(self, _db):
            pass

        async def getUserFromUserId(self, user_id: str):
            requested_user_ids.append(user_id)
            return sample_user

    from app.services import authenticationService as auth_module

    monkeypatch.setattr(auth_module, "UserService", FakeUserService)
    token_data = TokenModel(sub=sample_user.sub, email=sample_user.email)
    expired_access = auth_service._encodeAccessToken(
        token_data,
        timedelta(seconds=-1),
    )
    refresh_token = auth_service._encodeRefreshToken(token_data, timedelta(days=1))

    user = asyncio.run(
        auth_service.getUserFromAccessToken(expired_access, refresh_token),
    )

    assert user == sample_user
    assert requested_user_ids == [sample_user.sub]


def test_get_user_does_not_refresh_malformed_access_token(auth_service, monkeypatch):
    def fail_if_refresh_attempted(_refresh_token: str):
        raise AssertionError("malformed access tokens must not use refresh fallback")

    monkeypatch.setattr(
        auth_service,
        "generateAccessTokenFromRefreshToken",
        fail_if_refresh_attempted,
    )

    with pytest.raises(CredentialException):
        asyncio.run(
            auth_service.getUserFromAccessToken(
                "not-a-jwt",
                "refresh-token-should-not-be-used",
            ),
        )
