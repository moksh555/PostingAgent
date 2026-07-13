import asyncio
from datetime import UTC, datetime, timedelta

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


def test_refresh_token_uses_separate_signing_key_and_rejects_access_token():
    service = _service()
    data = TokenModel(sub="user-123", email="user@example.com")

    access_token = service._encodeAccessToken(data, timedelta(minutes=5))
    refresh_token = service._encodeRefreshToken(data, timedelta(days=1))

    with pytest.raises(CredentialException):
        service.generateAccessTokenFromRefreshToken(access_token)

    new_access = service.generateAccessTokenFromRefreshToken(refresh_token)
    decoded = jwt.decode(
        new_access.accessToken,
        config.AUTHENTICATION_SECRET_KEY,
        algorithms=[config.AUTHENTICATION_ALGORITHM],
    )

    assert new_access.tokenType == "ACCESS_TOKEN"
    assert decoded["sub"] == "user-123"
    assert decoded["email"] == "user@example.com"


def test_expired_refresh_token_is_not_authorized():
    expired_refresh = jwt.encode(
        {
            "sub": "user-123",
            "email": "user@example.com",
            "exp": datetime.now(UTC) - timedelta(seconds=1),
        },
        config.AUTHENTICATION_REFRESH_SECRET_KEY,
        algorithm=config.AUTHENTICATION_ALGORITHM,
    )

    with pytest.raises(NotAuthorized, match="Refresh token expired"):
        _service().generateAccessTokenFromRefreshToken(expired_refresh)


def test_refresh_token_without_subject_is_rejected():
    missing_subject = jwt.encode(
        {
            "email": "user@example.com",
            "exp": datetime.now(UTC) + timedelta(days=1),
        },
        config.AUTHENTICATION_REFRESH_SECRET_KEY,
        algorithm=config.AUTHENTICATION_ALGORITHM,
    )

    with pytest.raises(CredentialException):
        _service().generateAccessTokenFromRefreshToken(missing_subject)


def test_valid_access_token_loads_user_without_refresh(monkeypatch, sample_user):
    calls = {"refresh": 0, "lookup": []}

    class FakeUserService:
        def __init__(self, db):
            self.db = db

        async def getUserFromUserId(self, user_id):
            calls["lookup"].append(user_id)
            return sample_user

    service = _service()
    monkeypatch.setattr(auth_module, "UserService", FakeUserService)
    monkeypatch.setattr(
        service,
        "generateAccessTokenFromRefreshToken",
        lambda token: calls.__setitem__("refresh", calls["refresh"] + 1),
    )

    access_token = service._encodeAccessToken(
        TokenModel(sub=sample_user.sub, email=sample_user.email),
        timedelta(minutes=5),
    )

    user = asyncio.run(service.getUserFromAccessToken(access_token, "unused-refresh"))

    assert user == sample_user
    assert calls == {"refresh": 0, "lookup": [sample_user.sub]}


def test_expired_access_token_refreshes_then_retries_lookup(monkeypatch, sample_user):
    calls = {"lookup": []}

    class FakeUserService:
        def __init__(self, db):
            self.db = db

        async def getUserFromUserId(self, user_id):
            calls["lookup"].append(user_id)
            return sample_user

    service = _service()
    monkeypatch.setattr(auth_module, "UserService", FakeUserService)

    expired_access = service._encodeAccessToken(
        TokenModel(sub=sample_user.sub, email=sample_user.email),
        timedelta(seconds=-1),
    )
    refresh_token = service._encodeRefreshToken(
        TokenModel(sub=sample_user.sub, email=sample_user.email),
        timedelta(days=1),
    )

    user = asyncio.run(service.getUserFromAccessToken(expired_access, refresh_token))

    assert user == sample_user
    assert calls["lookup"] == [sample_user.sub]


def test_invalid_access_token_does_not_attempt_refresh(monkeypatch):
    service = _service()

    def fail_if_called(refresh_token):
        raise AssertionError("invalid access tokens must not trigger refresh")

    monkeypatch.setattr(service, "generateAccessTokenFromRefreshToken", fail_if_called)

    with pytest.raises(CredentialException):
        asyncio.run(service.getUserFromAccessToken("not-a-jwt", "refresh-token"))
