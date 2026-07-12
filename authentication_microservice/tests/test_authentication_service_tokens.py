from __future__ import annotations

import asyncio
from datetime import datetime, timedelta, timezone

import jwt
import pytest

from app.errorsHandler.tokenError import CredentialException
from app.models.tokenModel import TokenModel
from app.services import authenticationService as auth_module
from app.services.authenticationService import AuthenticationService
from configurations.config import config


def test_refresh_token_uses_distinct_key_and_rejects_access_token():
    auth = AuthenticationService(db=object())
    token_payload = TokenModel(sub="user-123", email="person@example.com")

    access_token = auth._encodeAccessToken(token_payload, timedelta(minutes=5))
    refresh_token = auth._encodeRefreshToken(token_payload, timedelta(days=1))

    with pytest.raises(CredentialException):
        auth.generateAccessTokenFromRefreshToken(access_token)

    new_access = auth.generateAccessTokenFromRefreshToken(refresh_token)

    assert new_access.tokenType == "ACCESS_TOKEN"
    decoded = jwt.decode(
        new_access.accessToken,
        config.AUTHENTICATION_SECRET_KEY,
        algorithms=[config.AUTHENTICATION_ALGORITHM],
    )
    assert decoded["sub"] == "user-123"
    assert decoded["email"] == "person@example.com"


def test_refresh_token_without_subject_is_rejected():
    auth = AuthenticationService(db=object())
    refresh_token = jwt.encode(
        {
            "email": "person@example.com",
            "exp": datetime.now(timezone.utc) + timedelta(days=1),
        },
        config.AUTHENTICATION_REFRESH_SECRET_KEY,
        algorithm=config.AUTHENTICATION_ALGORITHM,
    )

    with pytest.raises(CredentialException):
        auth.generateAccessTokenFromRefreshToken(refresh_token)


def test_expired_access_token_refreshes_and_retries_user_lookup(
    monkeypatch,
    sample_user,
):
    auth = AuthenticationService(db=object())
    token_payload = TokenModel(sub=sample_user.sub, email=sample_user.email)
    expired_access = auth._encodeAccessToken(token_payload, timedelta(seconds=-1))
    refresh_token = auth._encodeRefreshToken(token_payload, timedelta(days=1))
    looked_up_user_ids: list[str] = []

    class FakeUserService:
        def __init__(self, _db):
            pass

        async def getUserFromUserId(self, user_id: str):
            looked_up_user_ids.append(user_id)
            return sample_user

    monkeypatch.setattr(auth_module, "UserService", FakeUserService)

    user = asyncio.run(auth.getUserFromAccessToken(expired_access, refresh_token))

    assert user == sample_user
    assert looked_up_user_ids == [sample_user.sub]


def test_invalid_access_token_does_not_attempt_refresh(monkeypatch):
    auth = AuthenticationService(db=object())
    token_payload = TokenModel(sub="user-123", email="person@example.com")
    wrong_key_token = auth._encodeRefreshToken(token_payload, timedelta(days=1))

    def fail_if_called(_refresh_token: str):
        raise AssertionError("invalid access tokens must not be refreshed")

    monkeypatch.setattr(auth, "generateAccessTokenFromRefreshToken", fail_if_called)

    with pytest.raises(CredentialException):
        asyncio.run(
            auth.getUserFromAccessToken(
                wrong_key_token,
                "unused-refresh-token",
            )
        )
