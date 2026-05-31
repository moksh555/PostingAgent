import asyncio
from datetime import timedelta

import jwt
import pytest

from app.errorsHandler.loginError import NotAuthorized
from app.errorsHandler.tokenError import CredentialException
from app.models.tokenModel import TokenModel
from app.services import authenticationService as auth_module
from app.services.authenticationService import AuthenticationService
from configurations.config import config


def _service() -> AuthenticationService:
    return AuthenticationService(db=object())


def _token_data() -> TokenModel:
    return TokenModel(sub="user-123", email="user@example.com")


def test_generate_access_token_from_valid_refresh_token_preserves_claims():
    service = _service()
    refresh_token = service._encodeRefreshToken(_token_data(), timedelta(days=1))

    access_token = service.generateAccessTokenFromRefreshToken(refresh_token)

    payload = jwt.decode(
        access_token.accessToken,
        config.AUTHENTICATION_SECRET_KEY,
        algorithms=[config.AUTHENTICATION_ALGORITHM],
    )
    assert access_token.tokenType == "ACCESS_TOKEN"
    assert payload["sub"] == "user-123"
    assert payload["email"] == "user@example.com"


def test_expired_refresh_token_is_not_exchanged_for_access_token():
    service = _service()
    expired_refresh = service._encodeRefreshToken(_token_data(), timedelta(seconds=-1))

    with pytest.raises(NotAuthorized, match="Refresh token expired"):
        service.generateAccessTokenFromRefreshToken(expired_refresh)


def test_access_signed_token_cannot_be_used_as_refresh_token():
    service = _service()
    access_token = service._encodeAccessToken(_token_data(), timedelta(minutes=5))

    with pytest.raises(CredentialException):
        service.generateAccessTokenFromRefreshToken(access_token)


def test_expired_access_token_uses_refresh_token_before_loading_user(monkeypatch, sample_user):
    service = _service()
    expired_access = service._encodeAccessToken(_token_data(), timedelta(seconds=-1))
    refresh_token = service._encodeRefreshToken(_token_data(), timedelta(days=1))
    looked_up_user_ids: list[str] = []

    class FakeUserService:
        def __init__(self, db):
            self.db = db

        async def getUserFromUserId(self, user_id: str):
            looked_up_user_ids.append(user_id)
            return sample_user

    monkeypatch.setattr(auth_module, "UserService", FakeUserService)

    user = asyncio.run(service.getUserFromAccessToken(expired_access, refresh_token))

    assert user == sample_user
    assert looked_up_user_ids == ["user-123"]


def test_invalid_access_token_does_not_fall_back_to_refresh(monkeypatch):
    service = _service()
    invalid_access = service._encodeRefreshToken(_token_data(), timedelta(days=1))
    refresh_token = service._encodeRefreshToken(_token_data(), timedelta(days=1))
    refresh_attempted = False

    def fail_if_refreshed(token: str):
        nonlocal refresh_attempted
        refresh_attempted = True
        raise AssertionError("invalid access token should not trigger refresh")

    class FakeUserService:
        def __init__(self, db):
            self.db = db

        async def getUserFromUserId(self, user_id: str):
            raise AssertionError("invalid access token should not load a user")

    monkeypatch.setattr(auth_module, "UserService", FakeUserService)
    monkeypatch.setattr(service, "generateAccessTokenFromRefreshToken", fail_if_refreshed)

    with pytest.raises(CredentialException):
        asyncio.run(service.getUserFromAccessToken(invalid_access, refresh_token))
    assert refresh_attempted is False
