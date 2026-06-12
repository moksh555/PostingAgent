import asyncio
from datetime import timedelta

import jwt
import pytest

from app.errorsHandler.tokenError import CredentialException
from app.models.tokenModel import TokenModel
from app.services import authenticationService as auth_module
from configurations.config import config


def _install_fake_user_service(monkeypatch, returned_user):
    calls: list[str] = []

    class FakeUserService:
        def __init__(self, _db):
            pass

        async def getUserFromUserId(self, user_id: str):
            calls.append(user_id)
            return returned_user

    monkeypatch.setattr(auth_module, "UserService", FakeUserService)
    return calls


def test_refresh_token_issues_access_token_for_same_identity():
    service = auth_module.AuthenticationService(db=object())
    identity = TokenModel(sub="user-123", email="person@example.com")
    refresh_token = service._encodeRefreshToken(identity, timedelta(days=1))

    new_access = service.generateAccessTokenFromRefreshToken(refresh_token)

    assert new_access.tokenType == "ACCESS_TOKEN"
    decoded = jwt.decode(
        new_access.accessToken,
        config.AUTHENTICATION_SECRET_KEY,
        algorithms=[config.AUTHENTICATION_ALGORITHM],
    )
    assert decoded["sub"] == "user-123"
    assert decoded["email"] == "person@example.com"


def test_refresh_token_exchange_rejects_access_token_secret():
    service = auth_module.AuthenticationService(db=object())
    identity = TokenModel(sub="user-123", email="person@example.com")
    access_token = service._encodeAccessToken(identity, timedelta(minutes=5))

    with pytest.raises(CredentialException):
        service.generateAccessTokenFromRefreshToken(access_token)


def test_get_user_from_access_token_refreshes_after_expiry(monkeypatch, user_model):
    service = auth_module.AuthenticationService(db=object())
    identity = TokenModel(sub=user_model.sub, email=user_model.email)
    expired_access = service._encodeAccessToken(identity, timedelta(seconds=-1))
    refresh_token = service._encodeRefreshToken(identity, timedelta(days=1))
    calls = _install_fake_user_service(monkeypatch, user_model)

    result = asyncio.run(
        service.getUserFromAccessToken(expired_access, refresh_token),
    )

    assert result == user_model
    assert calls == [user_model.sub]


def test_get_user_from_access_token_does_not_refresh_invalid_access(monkeypatch, user_model):
    service = auth_module.AuthenticationService(db=object())
    refresh_token = service._encodeRefreshToken(
        TokenModel(sub=user_model.sub, email=user_model.email),
        timedelta(days=1),
    )
    calls = _install_fake_user_service(monkeypatch, user_model)

    def fail_if_refresh_is_attempted(_refresh_token: str):
        raise AssertionError("invalid access tokens must not trigger refresh")

    monkeypatch.setattr(
        service,
        "generateAccessTokenFromRefreshToken",
        fail_if_refresh_is_attempted,
    )
    invalid_access = jwt.encode(
        {"sub": user_model.sub, "email": user_model.email},
        "wrong-access-secret",
        algorithm=config.AUTHENTICATION_ALGORITHM,
    )

    with pytest.raises(CredentialException):
        asyncio.run(service.getUserFromAccessToken(invalid_access, refresh_token))

    assert calls == []
