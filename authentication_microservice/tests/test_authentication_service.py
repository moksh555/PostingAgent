import asyncio
from datetime import UTC, datetime, timedelta

import jwt  # type: ignore
import pytest

from app.errorsHandler.loginError import NotAuthorized
from app.errorsHandler.tokenError import CredentialException
from app.services import authenticationService as auth_module
from app.services.authenticationService import AuthenticationService
from configurations.config import config


def test_refresh_token_uses_refresh_secret_and_can_issue_access_token(tokenData):
    auth = AuthenticationService(db=None)  # type: ignore[arg-type]
    refresh_token = auth._encodeRefreshToken(tokenData, timedelta(minutes=5))

    with pytest.raises(CredentialException):
        auth._decode_access_token_payload(refresh_token)

    new_access = auth.generateAccessTokenFromRefreshToken(refresh_token)
    payload = auth._decode_access_token_payload(new_access.accessToken)

    assert new_access.tokenType == "ACCESS_TOKEN"
    assert payload["sub"] == tokenData.sub
    assert payload["email"] == tokenData.email


def test_expired_refresh_token_is_rejected(tokenData):
    auth = AuthenticationService(db=None)  # type: ignore[arg-type]
    expired_refresh = auth._encodeRefreshToken(tokenData, timedelta(seconds=-1))

    with pytest.raises(NotAuthorized, match="Refresh token expired"):
        auth.generateAccessTokenFromRefreshToken(expired_refresh)


def test_refresh_token_without_subject_is_rejected():
    auth = AuthenticationService(db=None)  # type: ignore[arg-type]
    refresh_without_sub = jwt.encode(
        {
            "email": "person@example.com",
            "exp": datetime.now(UTC) + timedelta(minutes=5),
        },
        config.AUTHENTICATION_REFRESH_SECRET_KEY,
        algorithm=config.AUTHENTICATION_ALGORITHM,
    )

    with pytest.raises(CredentialException):
        auth.generateAccessTokenFromRefreshToken(refresh_without_sub)


def test_expired_access_token_refreshes_then_loads_user(
    monkeypatch,
    sampleUser,
    tokenData,
):
    auth = AuthenticationService(db=None)  # type: ignore[arg-type]
    expired_access = auth._encodeAccessToken(tokenData, timedelta(seconds=-1))
    refresh_token = auth._encodeRefreshToken(tokenData, timedelta(minutes=5))
    user_ids_loaded: list[str] = []

    class FakeUserService:
        def __init__(self, db):
            self.db = db

        async def getUserFromUserId(self, user_id: str):
            user_ids_loaded.append(user_id)
            return sampleUser

    monkeypatch.setattr(auth_module, "UserService", FakeUserService)

    user = asyncio.run(auth.getUserFromAccessToken(expired_access, refresh_token))

    assert user == sampleUser
    assert user_ids_loaded == [tokenData.sub]


def test_invalid_access_token_does_not_attempt_refresh(monkeypatch, tokenData):
    auth = AuthenticationService(db=None)  # type: ignore[arg-type]
    refresh_token = auth._encodeRefreshToken(tokenData, timedelta(minutes=5))
    refresh_calls: list[str] = []

    def fail_if_refreshed(refresh_token_arg: str):
        refresh_calls.append(refresh_token_arg)
        raise AssertionError("invalid access tokens must not trigger refresh")

    monkeypatch.setattr(auth, "generateAccessTokenFromRefreshToken", fail_if_refreshed)

    with pytest.raises(CredentialException):
        asyncio.run(auth.getUserFromAccessToken(refresh_token, refresh_token))

    assert refresh_calls == []
