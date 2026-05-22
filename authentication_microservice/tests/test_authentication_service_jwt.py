import asyncio
from datetime import datetime, timedelta, timezone
from unittest.mock import AsyncMock, Mock

import jwt
import pytest

from app.errorsHandler.loginError import NotAuthorized
from app.errorsHandler.tokenError import CredentialException
from configurations.config import config


def test_access_and_refresh_tokens_use_separate_signing_secrets(auth_service, token_data):
    access_token = auth_service._encodeAccessToken(token_data, timedelta(minutes=5))
    refresh_token = auth_service._encodeRefreshToken(token_data, timedelta(days=1))

    access_payload = jwt.decode(
        access_token,
        config.AUTHENTICATION_SECRET_KEY,
        algorithms=[config.AUTHENTICATION_ALGORITHM],
    )
    refresh_payload = jwt.decode(
        refresh_token,
        config.AUTHENTICATION_REFRESH_SECRET_KEY,
        algorithms=[config.AUTHENTICATION_ALGORITHM],
    )

    assert access_payload["sub"] == token_data.sub
    assert refresh_payload["sub"] == token_data.sub
    with pytest.raises(jwt.InvalidTokenError):
        jwt.decode(
            refresh_token,
            config.AUTHENTICATION_SECRET_KEY,
            algorithms=[config.AUTHENTICATION_ALGORITHM],
        )
    with pytest.raises(jwt.InvalidTokenError):
        jwt.decode(
            access_token,
            config.AUTHENTICATION_REFRESH_SECRET_KEY,
            algorithms=[config.AUTHENTICATION_ALGORITHM],
        )


def test_generate_access_token_from_valid_refresh_token(auth_service, token_data):
    refresh_token = auth_service._encodeRefreshToken(token_data, timedelta(days=1))

    access_token = auth_service.generateAccessTokenFromRefreshToken(refresh_token)
    payload = jwt.decode(
        access_token.accessToken,
        config.AUTHENTICATION_SECRET_KEY,
        algorithms=[config.AUTHENTICATION_ALGORITHM],
    )

    assert access_token.tokenType == "ACCESS_TOKEN"
    assert payload["sub"] == token_data.sub
    assert payload["email"] == token_data.email


def test_expired_refresh_token_maps_to_not_authorized(auth_service, token_data):
    refresh_token = auth_service._encodeRefreshToken(token_data, timedelta(seconds=-1))

    with pytest.raises(NotAuthorized, match="Refresh token expired"):
        auth_service.generateAccessTokenFromRefreshToken(refresh_token)


@pytest.mark.parametrize(
    "payload",
    [
        {"email": "user@example.com"},
        {"sub": "", "email": "user@example.com"},
    ],
)
def test_refresh_token_without_subject_is_rejected(auth_service, payload):
    payload["exp"] = datetime.now(timezone.utc) + timedelta(days=1)
    refresh_token = jwt.encode(
        payload,
        config.AUTHENTICATION_REFRESH_SECRET_KEY,
        algorithm=config.AUTHENTICATION_ALGORITHM,
    )

    with pytest.raises(CredentialException):
        auth_service.generateAccessTokenFromRefreshToken(refresh_token)


def test_refresh_token_signed_with_access_secret_is_rejected(auth_service, token_data):
    wrong_secret_refresh = auth_service._encodeAccessToken(token_data, timedelta(days=1))

    with pytest.raises(CredentialException):
        auth_service.generateAccessTokenFromRefreshToken(wrong_secret_refresh)


def test_get_user_from_access_token_refreshes_only_for_expired_access(
    auth_service,
    monkeypatch,
    token_data,
    user_model,
):
    expired_access = auth_service._encodeAccessToken(token_data, timedelta(seconds=-1))
    valid_refresh = auth_service._encodeRefreshToken(token_data, timedelta(days=1))
    get_user = AsyncMock(return_value=user_model)
    monkeypatch.setattr(
        "app.services.authenticationService.UserService.getUserFromUserId",
        get_user,
    )

    result = asyncio.run(
        auth_service.getUserFromAccessToken(expired_access, valid_refresh),
    )

    assert result == user_model
    get_user.assert_awaited_once_with(token_data.sub)


def test_get_user_from_access_token_does_not_refresh_invalid_access(
    auth_service,
    monkeypatch,
    token_data,
):
    invalid_access = auth_service._encodeRefreshToken(token_data, timedelta(days=1))
    refresh_spy = Mock(side_effect=AssertionError("refresh should not be attempted"))
    monkeypatch.setattr(auth_service, "generateAccessTokenFromRefreshToken", refresh_spy)

    with pytest.raises(CredentialException):
        asyncio.run(auth_service.getUserFromAccessToken(invalid_access, "refresh-token"))

    refresh_spy.assert_not_called()
