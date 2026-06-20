import asyncio
from datetime import timedelta

import jwt
import pytest

from app.errorsHandler.loginError import NotAuthorized
from app.errorsHandler.tokenError import CredentialException
from app.models.tokenModel import TokenModel
from app.services.authenticationService import AuthenticationService
from configurations.config import config


def _decoded_access_claims(token: str) -> dict:
    return jwt.decode(
        token,
        config.AUTHENTICATION_SECRET_KEY,
        algorithms=[config.AUTHENTICATION_ALGORITHM],
    )


def test_refresh_token_generates_new_access_token_with_expected_claims():
    auth = AuthenticationService(db=object())
    refresh_token = auth._encodeRefreshToken(
        TokenModel(sub="user-123", email="user@example.com"),
        timedelta(days=1),
    )

    access_token = auth.generateAccessTokenFromRefreshToken(refresh_token)

    assert access_token.tokenType == "ACCESS_TOKEN"
    claims = _decoded_access_claims(access_token.accessToken)
    assert claims["sub"] == "user-123"
    assert claims["email"] == "user@example.com"


def test_access_token_cannot_be_used_as_refresh_token():
    auth = AuthenticationService(db=object())
    access_token = auth._encodeAccessToken(
        TokenModel(sub="user-123", email="user@example.com"),
        timedelta(minutes=1),
    )

    with pytest.raises(CredentialException):
        auth.generateAccessTokenFromRefreshToken(access_token)


def test_expired_access_token_uses_refresh_token_and_retries_user_lookup(
    monkeypatch,
    sample_user,
):
    from app.services import authenticationService as auth_module

    lookup_user_ids = []

    class FakeUserService:
        def __init__(self, db):
            self.db = db

        async def getUserFromUserId(self, user_id: str):
            lookup_user_ids.append(user_id)
            return sample_user

    monkeypatch.setattr(auth_module, "UserService", FakeUserService)
    auth = AuthenticationService(db=object())
    expired_access_token = auth._encodeAccessToken(
        TokenModel(sub=sample_user.sub, email=sample_user.email),
        timedelta(seconds=-1),
    )
    refresh_token = auth._encodeRefreshToken(
        TokenModel(sub=sample_user.sub, email=sample_user.email),
        timedelta(days=1),
    )

    user = asyncio.run(auth.getUserFromAccessToken(expired_access_token, refresh_token))

    assert user == sample_user
    assert lookup_user_ids == [sample_user.sub]


def test_malformed_access_token_does_not_attempt_refresh(monkeypatch):
    from app.services import authenticationService as auth_module

    class ExplodingUserService:
        def __init__(self, db):
            self.db = db

        async def getUserFromUserId(self, user_id: str):
            raise AssertionError("invalid access tokens should not reach user lookup")

    def fail_refresh(refresh_token: str):
        raise AssertionError("invalid access tokens should not be refreshed")

    monkeypatch.setattr(auth_module, "UserService", ExplodingUserService)
    auth = AuthenticationService(db=object())
    monkeypatch.setattr(auth, "generateAccessTokenFromRefreshToken", fail_refresh)

    with pytest.raises(CredentialException):
        asyncio.run(auth.getUserFromAccessToken("not-a-jwt", "refresh-token"))


def test_expired_refresh_token_is_not_authorized():
    auth = AuthenticationService(db=object())
    expired_refresh_token = auth._encodeRefreshToken(
        TokenModel(sub="user-123", email="user@example.com"),
        timedelta(seconds=-1),
    )

    with pytest.raises(NotAuthorized, match="Refresh token expired"):
        auth.generateAccessTokenFromRefreshToken(expired_refresh_token)
