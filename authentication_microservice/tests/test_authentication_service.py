import asyncio
from datetime import timedelta

import jwt
import pytest

from app.errorsHandler.loginError import NotAuthorized
from app.errorsHandler.tokenError import CredentialException
from app.models.tokenModel import TokenModel
from app.services.authenticationService import AuthenticationService
from configurations.config import config


def _decode_access_token(token: str) -> dict:
    return jwt.decode(
        token,
        config.AUTHENTICATION_SECRET_KEY,
        algorithms=[config.AUTHENTICATION_ALGORITHM],
    )


def test_refresh_token_generates_access_token_with_access_secret():
    auth = AuthenticationService(db=object())
    refresh_token = auth._encodeRefreshToken(
        TokenModel(sub="user-123", email="user@example.com"),
        timedelta(minutes=5),
    )

    access_token = auth.generateAccessTokenFromRefreshToken(refresh_token)

    assert access_token.tokenType == "ACCESS_TOKEN"
    payload = _decode_access_token(access_token.accessToken)
    assert payload["sub"] == "user-123"
    assert payload["email"] == "user@example.com"
    with pytest.raises(jwt.InvalidTokenError):
        jwt.decode(
            access_token.accessToken,
            config.AUTHENTICATION_REFRESH_SECRET_KEY,
            algorithms=[config.AUTHENTICATION_ALGORITHM],
        )


def test_refresh_exchange_rejects_access_token_signed_with_wrong_secret():
    auth = AuthenticationService(db=object())
    access_token = auth._encodeAccessToken(
        TokenModel(sub="user-123", email="user@example.com"),
        timedelta(minutes=5),
    )

    with pytest.raises(CredentialException):
        auth.generateAccessTokenFromRefreshToken(access_token)


def test_refresh_exchange_rejects_expired_refresh_token():
    auth = AuthenticationService(db=object())
    refresh_token = auth._encodeRefreshToken(
        TokenModel(sub="user-123", email="user@example.com"),
        timedelta(seconds=-1),
    )

    with pytest.raises(NotAuthorized, match="Refresh token expired"):
        auth.generateAccessTokenFromRefreshToken(refresh_token)


def test_refresh_exchange_requires_subject_claim():
    auth = AuthenticationService(db=object())
    refresh_token = jwt.encode(
        {"email": "user@example.com"},
        config.AUTHENTICATION_REFRESH_SECRET_KEY,
        algorithm=config.AUTHENTICATION_ALGORITHM,
    )

    with pytest.raises(CredentialException):
        auth.generateAccessTokenFromRefreshToken(refresh_token)


def test_get_user_from_access_token_refreshes_only_expired_access(monkeypatch, user_model):
    auth_module = pytest.importorskip("app.services.authenticationService")
    user_ids: list[str] = []

    class FakeUserService:
        def __init__(self, db):
            self.db = db

        async def getUserFromUserId(self, user_id: str):
            user_ids.append(user_id)
            return user_model

    monkeypatch.setattr(auth_module, "UserService", FakeUserService)
    auth = AuthenticationService(db=object())
    expired_access = auth._encodeAccessToken(
        TokenModel(sub=user_model.sub, email=user_model.email),
        timedelta(seconds=-1),
    )
    refresh_token = auth._encodeRefreshToken(
        TokenModel(sub=user_model.sub, email=user_model.email),
        timedelta(minutes=5),
    )

    result = asyncio.run(auth.getUserFromAccessToken(expired_access, refresh_token))

    assert result == user_model
    assert user_ids == [user_model.sub]


def test_get_user_from_access_token_does_not_refresh_malformed_access(monkeypatch):
    auth_module = pytest.importorskip("app.services.authenticationService")

    class FakeUserService:
        def __init__(self, db):
            self.db = db

        async def getUserFromUserId(self, user_id: str):
            raise AssertionError("invalid access tokens must not load users")

    def fail_refresh(refresh_token: str):
        raise AssertionError("invalid access tokens must not trigger refresh")

    monkeypatch.setattr(auth_module, "UserService", FakeUserService)
    auth = AuthenticationService(db=object())
    monkeypatch.setattr(auth, "generateAccessTokenFromRefreshToken", fail_refresh)

    with pytest.raises(CredentialException):
        asyncio.run(auth.getUserFromAccessToken("not-a-jwt", "refresh-token"))
