import asyncio
from datetime import datetime, timedelta, timezone

import jwt  # type: ignore
import pytest

from app.errorsHandler.loginError import NotAuthorized
from app.errorsHandler.tokenError import CredentialException
from app.models.tokenModel import TokenModel
from app.services import authenticationService as auth_module
from app.services.authenticationService import AuthenticationService
from configurations.config import config


@pytest.fixture
def token_data(user_model):
    return TokenModel(sub=user_model.sub, email=user_model.email)


@pytest.fixture
def auth_service_with_fake_users(monkeypatch, user_model):
    seen_user_ids: list[str] = []

    class FakeUserService:
        def __init__(self, _db):
            pass

        async def getUserFromUserId(self, user_id: str):
            seen_user_ids.append(user_id)
            return user_model

    monkeypatch.setattr(auth_module, "UserService", FakeUserService)
    return AuthenticationService(db=object()), seen_user_ids


def test_refresh_token_generates_access_token_signed_with_access_secret(
    auth_service_with_fake_users,
    token_data,
):
    service, _seen_user_ids = auth_service_with_fake_users
    refresh_token = service._encodeRefreshToken(token_data, timedelta(minutes=5))

    new_access_token = service.generateAccessTokenFromRefreshToken(refresh_token)

    assert new_access_token.tokenType == "ACCESS_TOKEN"
    payload = jwt.decode(
        new_access_token.accessToken,
        config.AUTHENTICATION_SECRET_KEY,
        algorithms=[config.AUTHENTICATION_ALGORITHM],
    )
    assert payload["sub"] == token_data.sub
    assert payload["email"] == token_data.email


def test_refresh_flow_rejects_access_token_signed_with_access_secret(
    auth_service_with_fake_users,
    token_data,
):
    service, _seen_user_ids = auth_service_with_fake_users
    access_token = service._encodeAccessToken(token_data, timedelta(minutes=5))

    with pytest.raises(CredentialException):
        service.generateAccessTokenFromRefreshToken(access_token)


def test_expired_access_token_uses_refresh_token_then_loads_user(
    auth_service_with_fake_users,
    token_data,
    user_model,
):
    service, seen_user_ids = auth_service_with_fake_users
    expired_access_token = service._encodeAccessToken(token_data, timedelta(seconds=-1))
    refresh_token = service._encodeRefreshToken(token_data, timedelta(minutes=5))

    result = asyncio.run(
        service.getUserFromAccessToken(expired_access_token, refresh_token),
    )

    assert result == user_model
    assert seen_user_ids == [user_model.sub]


def test_invalid_access_token_does_not_attempt_refresh(
    auth_service_with_fake_users,
    token_data,
):
    service, seen_user_ids = auth_service_with_fake_users
    bad_access_token = jwt.encode(
        {
            "sub": token_data.sub,
            "email": token_data.email,
            "exp": datetime.now(timezone.utc) + timedelta(minutes=5),
        },
        "wrong-access-secret-with-32-bytes-minimum",
        algorithm=config.AUTHENTICATION_ALGORITHM,
    )
    valid_refresh_token = service._encodeRefreshToken(token_data, timedelta(minutes=5))

    with pytest.raises(CredentialException):
        asyncio.run(service.getUserFromAccessToken(bad_access_token, valid_refresh_token))

    assert seen_user_ids == []


def test_expired_refresh_token_raises_not_authorized(
    auth_service_with_fake_users,
    token_data,
):
    service, _seen_user_ids = auth_service_with_fake_users
    expired_refresh_token = service._encodeRefreshToken(token_data, timedelta(seconds=-1))

    with pytest.raises(NotAuthorized, match="Refresh token expired"):
        service.generateAccessTokenFromRefreshToken(expired_refresh_token)
