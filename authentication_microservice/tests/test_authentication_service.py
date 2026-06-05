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


def _run(coro):
    return asyncio.run(coro)


def test_refresh_token_generates_new_access_token_with_expected_claims():
    service = AuthenticationService(db=object())
    refresh_token = service._encodeRefreshToken(
        TokenModel(sub="user-123", email="user@example.com"),
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
    assert payload["email"] == "user@example.com"


def test_refresh_rejects_access_token_signed_with_wrong_secret():
    service = AuthenticationService(db=object())
    access_token = service._encodeAccessToken(
        TokenModel(sub="user-123", email="user@example.com"),
        timedelta(minutes=5),
    )

    with pytest.raises(CredentialException):
        service.generateAccessTokenFromRefreshToken(access_token)


@pytest.mark.parametrize(
    "payload",
    [
        {"email": "user@example.com"},
        {"sub": "", "email": "user@example.com"},
    ],
)
def test_refresh_rejects_tokens_without_user_identity(payload):
    service = AuthenticationService(db=object())
    token = jwt.encode(
        {
            **payload,
            "exp": datetime.now(timezone.utc) + timedelta(days=1),
        },
        config.AUTHENTICATION_REFRESH_SECRET_KEY,
        algorithm=config.AUTHENTICATION_ALGORITHM,
    )

    with pytest.raises(CredentialException):
        service.generateAccessTokenFromRefreshToken(token)


def test_refresh_rejects_expired_refresh_token():
    service = AuthenticationService(db=object())
    expired_refresh = service._encodeRefreshToken(
        TokenModel(sub="user-123", email="user@example.com"),
        timedelta(seconds=-1),
    )

    with pytest.raises(NotAuthorized, match="Refresh token expired"):
        service.generateAccessTokenFromRefreshToken(expired_refresh)


def test_get_user_refreshes_only_when_access_token_is_expired(monkeypatch, sample_user):
    service = AuthenticationService(db=object())
    seen_user_ids: list[str] = []

    class FakeUserService:
        def __init__(self, db):
            self.db = db

        async def getUserFromUserId(self, user_id: str):
            seen_user_ids.append(user_id)
            return sample_user

    monkeypatch.setattr(auth_module, "UserService", FakeUserService)
    expired_access = service._encodeAccessToken(
        TokenModel(sub=sample_user.sub, email=sample_user.email),
        timedelta(seconds=-1),
    )
    refresh_token = service._encodeRefreshToken(
        TokenModel(sub=sample_user.sub, email=sample_user.email),
        timedelta(days=1),
    )

    user = _run(service.getUserFromAccessToken(expired_access, refresh_token))

    assert user == sample_user
    assert seen_user_ids == [sample_user.sub]


def test_get_user_does_not_refresh_invalid_access_token(monkeypatch, sample_user):
    service = AuthenticationService(db=object())
    invalid_access = jwt.encode(
        {
            "sub": sample_user.sub,
            "email": sample_user.email,
            "exp": datetime.now(timezone.utc) + timedelta(minutes=5),
        },
        "wrong-access-secret-with-enough-entropy",
        algorithm=config.AUTHENTICATION_ALGORITHM,
    )

    def fail_if_called(refresh_token: str):  # pragma: no cover - should never run
        raise AssertionError("Invalid access tokens must not trigger refresh")

    monkeypatch.setattr(service, "generateAccessTokenFromRefreshToken", fail_if_called)

    with pytest.raises(CredentialException):
        _run(service.getUserFromAccessToken(invalid_access, "refresh-token"))
