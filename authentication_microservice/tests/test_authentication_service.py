import asyncio
from datetime import datetime, timedelta, timezone

import jwt
import pytest

from app.errorsHandler.loginError import NotAuthorized
from app.errorsHandler.tokenError import CredentialException
from app.models.tokenModel import TokenModel
from app.services import authenticationService as auth_module
from configurations.config import config


def test_generate_access_token_from_valid_refresh_token(auth_service, token_model):
    refresh_token = auth_service._encodeRefreshToken(token_model, timedelta(days=1))

    access_token = auth_service.generateAccessTokenFromRefreshToken(refresh_token)

    assert access_token.tokenType == "ACCESS_TOKEN"
    payload = jwt.decode(
        access_token.accessToken,
        config.AUTHENTICATION_SECRET_KEY,
        algorithms=[config.AUTHENTICATION_ALGORITHM],
    )
    assert payload["sub"] == token_model.sub
    assert payload["email"] == token_model.email


def test_expired_refresh_token_is_rejected(auth_service, token_model):
    refresh_token = auth_service._encodeRefreshToken(token_model, timedelta(days=-1))

    with pytest.raises(NotAuthorized, match="Refresh token expired"):
        auth_service.generateAccessTokenFromRefreshToken(refresh_token)


def test_refresh_token_signed_with_access_secret_is_rejected(auth_service, token_model):
    wrong_secret_token = auth_service._encodeAccessToken(token_model, timedelta(minutes=5))

    with pytest.raises(CredentialException):
        auth_service.generateAccessTokenFromRefreshToken(wrong_secret_token)


def test_refresh_token_without_subject_is_rejected(auth_service):
    refresh_token = jwt.encode(
        {
            "email": "user@example.com",
            "exp": datetime.now(timezone.utc) + timedelta(days=1),
        },
        config.AUTHENTICATION_REFRESH_SECRET_KEY,
        algorithm=config.AUTHENTICATION_ALGORITHM,
    )

    with pytest.raises(CredentialException):
        auth_service.generateAccessTokenFromRefreshToken(refresh_token)


def test_get_user_from_expired_access_token_silently_uses_refresh_token(
    auth_service, token_model, user_model, monkeypatch
):
    expired_access_token = auth_service._encodeAccessToken(
        token_model,
        timedelta(minutes=-1),
    )
    refresh_token = auth_service._encodeRefreshToken(token_model, timedelta(days=1))
    loaded_user_ids: list[str] = []

    async def fake_get_user_from_user_id(self, user_id: str):
        loaded_user_ids.append(user_id)
        return user_model

    monkeypatch.setattr(
        auth_module.UserService,
        "getUserFromUserId",
        fake_get_user_from_user_id,
    )

    result = asyncio.run(
        auth_service.getUserFromAccessToken(expired_access_token, refresh_token)
    )

    assert result == user_model
    assert loaded_user_ids == [token_model.sub]


def test_get_user_from_bad_access_token_does_not_attempt_refresh(
    auth_service, token_model, monkeypatch
):
    wrong_secret_access_token = auth_service._encodeRefreshToken(
        token_model,
        timedelta(days=1),
    )

    def fail_if_refresh_attempted(refresh_token: str):
        raise AssertionError("refresh should only run for expired access tokens")

    monkeypatch.setattr(
        auth_service,
        "generateAccessTokenFromRefreshToken",
        fail_if_refresh_attempted,
    )

    with pytest.raises(CredentialException):
        asyncio.run(
            auth_service.getUserFromAccessToken(
                wrong_secret_access_token,
                "unused-refresh-token",
            )
        )
