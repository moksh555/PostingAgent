import asyncio
from datetime import UTC, datetime, timedelta

import jwt
import pytest

from app.errorsHandler.loginError import NotAuthorized
from app.errorsHandler.tokenError import CredentialException
from app.models.tokenModel import TokenModel
from app.services.authenticationService import AuthenticationService
from configurations.config import config


def _service() -> AuthenticationService:
    return AuthenticationService(db=object())


def test_refresh_token_issues_access_token_with_access_secret():
    service = _service()
    refresh_token = service._encodeRefreshToken(
        TokenModel(sub="user-123", email="person@example.com"),
        timedelta(days=1),
    )

    access_token = service.generateAccessTokenFromRefreshToken(refresh_token)

    assert access_token.tokenType == "ACCESS_TOKEN"
    payload = jwt.decode(
        access_token.accessToken,
        config.AUTHENTICATION_SECRET_KEY,
        algorithms=[config.AUTHENTICATION_ALGORITHM],
    )
    assert payload["sub"] == "user-123"
    assert payload["email"] == "person@example.com"
    with pytest.raises(jwt.InvalidTokenError):
        jwt.decode(
            access_token.accessToken,
            config.AUTHENTICATION_REFRESH_SECRET_KEY,
            algorithms=[config.AUTHENTICATION_ALGORITHM],
        )


def test_access_token_cannot_be_reused_as_refresh_token():
    service = _service()
    access_token = service._encodeAccessToken(
        TokenModel(sub="user-123", email="person@example.com"),
        timedelta(minutes=1),
    )

    with pytest.raises(CredentialException):
        service.generateAccessTokenFromRefreshToken(access_token)


def test_expired_refresh_token_is_not_exchanged_for_access_token():
    service = _service()
    refresh_token = service._encodeRefreshToken(
        TokenModel(sub="user-123", email="person@example.com"),
        timedelta(seconds=-1),
    )

    with pytest.raises(NotAuthorized, match="Refresh token expired"):
        service.generateAccessTokenFromRefreshToken(refresh_token)


def test_refresh_token_missing_subject_is_rejected():
    refresh_token = jwt.encode(
        {
            "email": "person@example.com",
            "exp": datetime.now(UTC) + timedelta(minutes=5),
        },
        config.AUTHENTICATION_REFRESH_SECRET_KEY,
        algorithm=config.AUTHENTICATION_ALGORITHM,
    )

    with pytest.raises(CredentialException):
        _service().generateAccessTokenFromRefreshToken(refresh_token)


def test_valid_access_token_loads_user_without_refresh(monkeypatch, user_model):
    import app.services.authenticationService as auth_module

    requested_user_ids = []

    class FakeUserService:
        def __init__(self, db):
            self.db = db

        async def getUserFromUserId(self, user_id):
            requested_user_ids.append(user_id)
            return user_model

    service = _service()
    monkeypatch.setattr(auth_module, "UserService", FakeUserService)
    access_token = service._encodeAccessToken(
        TokenModel(sub=user_model.sub, email=user_model.email),
        timedelta(minutes=1),
    )

    result = asyncio.run(
        service.getUserFromAccessToken(access_token, refreshToken="unused-refresh"),
    )

    assert result == user_model
    assert requested_user_ids == [user_model.sub]


def test_expired_access_token_refreshes_once_then_loads_user(monkeypatch, user_model):
    import app.services.authenticationService as auth_module

    requested_user_ids = []

    class FakeUserService:
        def __init__(self, db):
            self.db = db

        async def getUserFromUserId(self, user_id):
            requested_user_ids.append(user_id)
            return user_model

    service = _service()
    monkeypatch.setattr(auth_module, "UserService", FakeUserService)
    expired_access_token = service._encodeAccessToken(
        TokenModel(sub=user_model.sub, email=user_model.email),
        timedelta(seconds=-1),
    )
    refresh_token = service._encodeRefreshToken(
        TokenModel(sub=user_model.sub, email=user_model.email),
        timedelta(days=1),
    )

    result = asyncio.run(
        service.getUserFromAccessToken(expired_access_token, refresh_token),
    )

    assert result == user_model
    assert requested_user_ids == [user_model.sub]


def test_invalid_access_token_does_not_attempt_refresh(monkeypatch):
    service = _service()

    def fail_if_refreshed(refresh_token):
        raise AssertionError("invalid access tokens must not be refreshed")

    monkeypatch.setattr(
        service,
        "generateAccessTokenFromRefreshToken",
        fail_if_refreshed,
    )

    with pytest.raises(CredentialException):
        asyncio.run(
            service.getUserFromAccessToken(
                accessToken="not-a-valid-jwt",
                refreshToken="refresh-token",
            ),
        )
