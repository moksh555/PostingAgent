import asyncio
from datetime import datetime, timedelta, timezone

import jwt  # type: ignore
import pytest

from app.errorsHandler.loginError import NotAuthorized
from app.errorsHandler.tokenError import CredentialException
from app.models.tokenModel import TokenModel
from app.services import authenticationService as auth_module
from configurations.config import config


def _token_data() -> TokenModel:
    return TokenModel(sub="user-123", email="user@example.com")


def test_refresh_exchange_rejects_access_token(auth_service):
    access_token = auth_service._encodeAccessToken(_token_data(), timedelta(minutes=5))

    with pytest.raises(CredentialException):
        auth_service.generateAccessTokenFromRefreshToken(access_token)


def test_expired_refresh_token_is_not_exchanged(auth_service):
    refresh_token = auth_service._encodeRefreshToken(_token_data(), timedelta(seconds=-1))

    with pytest.raises(NotAuthorized, match="Refresh token expired"):
        auth_service.generateAccessTokenFromRefreshToken(refresh_token)


def test_refresh_token_without_subject_is_rejected(auth_service):
    refresh_token = jwt.encode(
        {
            "email": "user@example.com",
            "exp": datetime.now(timezone.utc) + timedelta(minutes=5),
        },
        config.AUTHENTICATION_REFRESH_SECRET_KEY,
        algorithm=config.AUTHENTICATION_ALGORITHM,
    )

    with pytest.raises(CredentialException):
        auth_service.generateAccessTokenFromRefreshToken(refresh_token)


def test_refresh_exchange_issues_access_token_signed_with_access_key(auth_service):
    refresh_token = auth_service._encodeRefreshToken(_token_data(), timedelta(minutes=5))

    access_token = auth_service.generateAccessTokenFromRefreshToken(refresh_token)

    assert access_token.tokenType == "ACCESS_TOKEN"
    payload = jwt.decode(
        access_token.accessToken,
        config.AUTHENTICATION_SECRET_KEY,
        algorithms=[config.AUTHENTICATION_ALGORITHM],
    )
    assert payload["sub"] == "user-123"
    with pytest.raises(jwt.InvalidTokenError):
        jwt.decode(
            access_token.accessToken,
            config.AUTHENTICATION_REFRESH_SECRET_KEY,
            algorithms=[config.AUTHENTICATION_ALGORITHM],
        )


def test_valid_access_token_loads_user_without_refresh(
    auth_service,
    sample_user,
    monkeypatch,
):
    seen_user_ids: list[str] = []

    class FakeUserService:
        def __init__(self, _db):
            pass

        async def getUserFromUserId(self, user_id: str):
            seen_user_ids.append(user_id)
            return sample_user

    monkeypatch.setattr(auth_module, "UserService", FakeUserService)
    monkeypatch.setattr(
        auth_service,
        "generateAccessTokenFromRefreshToken",
        lambda _token: pytest.fail("valid access token should not be refreshed"),
    )
    access_token = auth_service._encodeAccessToken(_token_data(), timedelta(minutes=5))

    result = asyncio.run(
        auth_service.getUserFromAccessToken(access_token, "unused-refresh-token"),
    )

    assert result == sample_user
    assert seen_user_ids == ["user-123"]


def test_expired_access_token_refreshes_then_loads_user(
    auth_service,
    sample_user,
    monkeypatch,
):
    seen_user_ids: list[str] = []

    class FakeUserService:
        def __init__(self, _db):
            pass

        async def getUserFromUserId(self, user_id: str):
            seen_user_ids.append(user_id)
            return sample_user

    monkeypatch.setattr(auth_module, "UserService", FakeUserService)
    expired_access_token = auth_service._encodeAccessToken(
        _token_data(),
        timedelta(seconds=-1),
    )
    refresh_token = auth_service._encodeRefreshToken(_token_data(), timedelta(minutes=5))

    result = asyncio.run(
        auth_service.getUserFromAccessToken(expired_access_token, refresh_token),
    )

    assert result == sample_user
    assert seen_user_ids == ["user-123"]


def test_invalid_access_token_does_not_attempt_refresh(auth_service, monkeypatch):
    access_token_signed_with_refresh_key = auth_service._encodeRefreshToken(
        _token_data(),
        timedelta(minutes=5),
    )
    monkeypatch.setattr(
        auth_service,
        "generateAccessTokenFromRefreshToken",
        lambda _token: pytest.fail("invalid access tokens must not be refreshed"),
    )

    with pytest.raises(CredentialException):
        asyncio.run(
            auth_service.getUserFromAccessToken(
                access_token_signed_with_refresh_key,
                "refresh-token",
            ),
        )
