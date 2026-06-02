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


@pytest.fixture
def auth_service():
    return AuthenticationService(db=object())


def decode_access_token(token: str) -> dict:
    return jwt.decode(
        token,
        config.AUTHENTICATION_SECRET_KEY,
        algorithms=[config.AUTHENTICATION_ALGORITHM],
    )


def test_generate_access_token_from_refresh_token_preserves_identity(auth_service):
    refresh_token = auth_service._encodeRefreshToken(
        TokenModel(sub="user-123", email="user@example.com"),
        timedelta(days=1),
    )

    access_token = auth_service.generateAccessTokenFromRefreshToken(refresh_token)

    assert access_token.tokenType == "ACCESS_TOKEN"
    payload = decode_access_token(access_token.accessToken)
    assert payload["sub"] == "user-123"
    assert payload["email"] == "user@example.com"


def test_generate_access_token_from_refresh_token_rejects_access_token_secret(
    auth_service,
):
    access_token = auth_service._encodeAccessToken(
        TokenModel(sub="user-123", email="user@example.com"),
        timedelta(minutes=1),
    )

    with pytest.raises(CredentialException):
        auth_service.generateAccessTokenFromRefreshToken(access_token)


def test_generate_access_token_from_refresh_token_requires_subject(auth_service):
    refresh_token_without_sub = jwt.encode(
        {"email": "user@example.com"},
        config.AUTHENTICATION_REFRESH_SECRET_KEY,
        algorithm=config.AUTHENTICATION_ALGORITHM,
    )

    with pytest.raises(CredentialException):
        auth_service.generateAccessTokenFromRefreshToken(refresh_token_without_sub)


def test_generate_access_token_from_refresh_token_rejects_expired_refresh_token(
    auth_service,
):
    expired_refresh_token = auth_service._encodeRefreshToken(
        TokenModel(sub="user-123", email="user@example.com"),
        timedelta(seconds=-1),
    )

    with pytest.raises(NotAuthorized, match="Refresh token expired"):
        auth_service.generateAccessTokenFromRefreshToken(expired_refresh_token)


def test_get_user_from_access_token_refreshes_only_expired_access_tokens(
    auth_service,
    monkeypatch,
    sample_user,
):
    requested_user_ids: list[str] = []

    class FakeUserService:
        def __init__(self, db):
            self.db = db

        async def getUserFromUserId(self, user_id: str):
            requested_user_ids.append(user_id)
            return sample_user

    monkeypatch.setattr(auth_module, "UserService", FakeUserService)
    expired_access_token = auth_service._encodeAccessToken(
        TokenModel(sub=sample_user.sub, email=sample_user.email),
        timedelta(seconds=-1),
    )
    refresh_token = auth_service._encodeRefreshToken(
        TokenModel(sub=sample_user.sub, email=sample_user.email),
        timedelta(days=1),
    )

    user = asyncio.run(
        auth_service.getUserFromAccessToken(
            expired_access_token,
            refresh_token,
        )
    )

    assert user == sample_user
    assert requested_user_ids == [sample_user.sub]


def test_get_user_from_access_token_does_not_refresh_invalid_access_tokens(
    auth_service,
    monkeypatch,
):
    refresh_attempted = False

    def fail_if_refresh_is_attempted(refresh_token: str):
        nonlocal refresh_attempted
        refresh_attempted = True
        raise AssertionError("invalid access tokens must not trigger refresh")

    monkeypatch.setattr(
        auth_service,
        "generateAccessTokenFromRefreshToken",
        fail_if_refresh_is_attempted,
    )
    refresh_token = auth_service._encodeRefreshToken(
        TokenModel(sub="user-123", email="user@example.com"),
        timedelta(days=1),
    )

    with pytest.raises(CredentialException):
        asyncio.run(
            auth_service.getUserFromAccessToken(
                "not-a-jwt",
                refresh_token,
            )
        )
    assert refresh_attempted is False
