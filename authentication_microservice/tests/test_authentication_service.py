import asyncio
from datetime import datetime, timedelta, timezone

import jwt
import pytest

from app.errorsHandler.loginError import NotAuthorized
from app.errorsHandler.tokenError import CredentialException
from app.models.tokenModel import TokenModel
from app.services import authenticationService as auth_module
from app.services.authenticationService import AuthenticationService
from configurations.config import config


@pytest.fixture
def auth_service():
    return AuthenticationService(db=None)


@pytest.fixture
def token_data():
    return TokenModel(sub="user-123", email="user@example.com")


@pytest.fixture
def patched_user_service(monkeypatch, sample_user):
    calls: list[str] = []

    class FakeUserService:
        def __init__(self, db):
            self.db = db

        async def getUserFromUserId(self, user_id: str):
            calls.append(user_id)
            return sample_user.model_copy(update={"sub": user_id})

    monkeypatch.setattr(auth_module, "UserService", FakeUserService)
    return calls


def test_refresh_token_uses_refresh_secret_and_mints_access_token(auth_service, token_data):
    refresh_token = auth_service._encodeRefreshToken(token_data, timedelta(minutes=5))

    with pytest.raises(jwt.InvalidTokenError):
        jwt.decode(
            refresh_token,
            config.AUTHENTICATION_SECRET_KEY,
            algorithms=[config.AUTHENTICATION_ALGORITHM],
        )

    access_token = auth_service.generateAccessTokenFromRefreshToken(refresh_token)
    payload = jwt.decode(
        access_token.accessToken,
        config.AUTHENTICATION_SECRET_KEY,
        algorithms=[config.AUTHENTICATION_ALGORITHM],
    )

    assert access_token.tokenType == "ACCESS_TOKEN"
    assert payload["sub"] == token_data.sub
    assert payload["email"] == token_data.email


def test_expired_refresh_token_is_rejected(auth_service, token_data):
    expired_refresh = auth_service._encodeRefreshToken(
        token_data,
        timedelta(seconds=-1),
    )

    with pytest.raises(NotAuthorized, match="Refresh token expired"):
        auth_service.generateAccessTokenFromRefreshToken(expired_refresh)


def test_refresh_token_requires_subject_claim(auth_service):
    payload = {
        "email": "user@example.com",
        "exp": datetime.now(timezone.utc) + timedelta(minutes=5),
    }
    refresh_without_sub = jwt.encode(
        payload,
        config.AUTHENTICATION_REFRESH_SECRET_KEY,
        algorithm=config.AUTHENTICATION_ALGORITHM,
    )

    with pytest.raises(CredentialException):
        auth_service.generateAccessTokenFromRefreshToken(refresh_without_sub)


def test_expired_access_token_refreshes_then_loads_user(
    auth_service,
    token_data,
    patched_user_service,
):
    expired_access = auth_service._encodeAccessToken(token_data, timedelta(seconds=-1))
    refresh_token = auth_service._encodeRefreshToken(token_data, timedelta(minutes=5))

    user = asyncio.run(
        auth_service.getUserFromAccessToken(expired_access, refresh_token),
    )

    assert user.sub == token_data.sub
    assert patched_user_service == [token_data.sub]


def test_invalid_access_token_does_not_use_refresh_token(
    auth_service,
    token_data,
    patched_user_service,
    monkeypatch,
):
    wrong_key_access = auth_service._encodeRefreshToken(token_data, timedelta(minutes=5))
    valid_refresh = auth_service._encodeRefreshToken(token_data, timedelta(minutes=5))
    refresh_attempts: list[str] = []

    def fail_if_refreshed(refresh_token: str):
        refresh_attempts.append(refresh_token)
        raise AssertionError("invalid access tokens must not trigger refresh")

    monkeypatch.setattr(
        auth_service,
        "generateAccessTokenFromRefreshToken",
        fail_if_refreshed,
    )

    with pytest.raises(CredentialException):
        asyncio.run(auth_service.getUserFromAccessToken(wrong_key_access, valid_refresh))

    assert refresh_attempts == []
    assert patched_user_service == []
