import asyncio
from datetime import timedelta

import jwt
import pytest

from app.errorsHandler.loginError import NotAuthorized
from app.errorsHandler.tokenError import CredentialException
from app.models.tokenModel import TokenModel
from configurations.config import config


def test_refresh_exchange_rejects_access_tokens(auth_service):
    access_token = auth_service._encodeAccessToken(
        TokenModel(sub="user-123", email="user@example.com"),
        timedelta(minutes=5),
    )

    with pytest.raises(CredentialException):
        auth_service.generateAccessTokenFromRefreshToken(access_token)


def test_refresh_exchange_rejects_expired_refresh_tokens(auth_service):
    refresh_token = auth_service._encodeRefreshToken(
        TokenModel(sub="user-123", email="user@example.com"),
        timedelta(seconds=-1),
    )

    with pytest.raises(NotAuthorized, match="Refresh token expired"):
        auth_service.generateAccessTokenFromRefreshToken(refresh_token)


def test_refresh_exchange_requires_subject_claim(auth_service):
    refresh_token = jwt.encode(
        {"email": "user@example.com"},
        config.AUTHENTICATION_REFRESH_SECRET_KEY,
        algorithm=config.AUTHENTICATION_ALGORITHM,
    )

    with pytest.raises(CredentialException):
        auth_service.generateAccessTokenFromRefreshToken(refresh_token)


def test_expired_access_token_uses_refresh_then_loads_user(
    auth_service,
    monkeypatch,
    user_model_factory,
):
    loaded_user_ids: list[str] = []

    class FakeUserService:
        def __init__(self, _db):
            pass

        async def getUserFromUserId(self, user_id: str):
            loaded_user_ids.append(user_id)
            return user_model_factory(sub=user_id)

    monkeypatch.setattr(
        "app.services.authenticationService.UserService",
        FakeUserService,
    )
    token_model = TokenModel(sub="user-123", email="user@example.com")
    expired_access = auth_service._encodeAccessToken(
        token_model,
        timedelta(seconds=-1),
    )
    refresh_token = auth_service._encodeRefreshToken(
        token_model,
        timedelta(days=1),
    )

    user = asyncio.run(
        auth_service.getUserFromAccessToken(expired_access, refresh_token),
    )

    assert user.sub == "user-123"
    assert loaded_user_ids == ["user-123"]


def test_invalid_access_token_does_not_attempt_refresh(
    auth_service,
    monkeypatch,
):
    class FakeUserService:
        def __init__(self, _db):
            pass

        async def getUserFromUserId(self, _user_id: str):
            raise AssertionError("invalid access tokens must not load users")

    def fail_refresh(_refresh_token: str):
        raise AssertionError("invalid access tokens must not be refreshed")

    monkeypatch.setattr(
        "app.services.authenticationService.UserService",
        FakeUserService,
    )
    monkeypatch.setattr(
        auth_service,
        "generateAccessTokenFromRefreshToken",
        fail_refresh,
    )

    with pytest.raises(CredentialException):
        asyncio.run(
            auth_service.getUserFromAccessToken(
                "not-a-jwt",
                "refresh-token",
            ),
        )
