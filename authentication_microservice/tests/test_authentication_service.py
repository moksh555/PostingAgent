import asyncio
from datetime import timedelta

import jwt  # type: ignore
import pytest

from app.errorsHandler.loginError import NotAuthorized
from app.errorsHandler.tokenError import CredentialException
from app.models.tokenModel import TokenModel
from app.services import authenticationService as auth_module
from app.services.authenticationService import AuthenticationService
from configurations.config import config


@pytest.fixture
def auth_service():
    return AuthenticationService(db=None)  # type: ignore[arg-type]


@pytest.fixture
def token_data(sample_user):
    return TokenModel(sub=sample_user.sub, email=sample_user.email)


@pytest.fixture
def fake_user_service(monkeypatch, sample_user):
    calls: list[str] = []

    class FakeUserService:
        def __init__(self, db):
            self.db = db

        async def getUserFromUserId(self, user_id: str):
            calls.append(user_id)
            assert user_id == sample_user.sub
            return sample_user

    monkeypatch.setattr(auth_module, "UserService", FakeUserService)
    return calls


def test_generate_access_token_from_refresh_token_preserves_identity(
    auth_service,
    token_data,
):
    refresh_token = auth_service._encodeRefreshToken(token_data, timedelta(days=1))

    access_token = auth_service.generateAccessTokenFromRefreshToken(refresh_token)

    assert access_token.tokenType == "ACCESS_TOKEN"
    payload = jwt.decode(
        access_token.accessToken,
        config.AUTHENTICATION_SECRET_KEY,
        algorithms=[config.AUTHENTICATION_ALGORITHM],
    )
    assert payload["sub"] == token_data.sub
    assert payload["email"] == token_data.email


def test_expired_refresh_token_is_not_exchanged(auth_service, token_data):
    expired_refresh_token = auth_service._encodeRefreshToken(
        token_data,
        timedelta(seconds=-1),
    )

    with pytest.raises(NotAuthorized, match="Refresh token expired"):
        auth_service.generateAccessTokenFromRefreshToken(expired_refresh_token)


def test_get_user_from_expired_access_token_uses_refresh_token(
    auth_service,
    fake_user_service,
    sample_user,
    token_data,
):
    expired_access_token = auth_service._encodeAccessToken(
        token_data,
        timedelta(seconds=-1),
    )
    refresh_token = auth_service._encodeRefreshToken(token_data, timedelta(days=1))

    user = asyncio.run(
        auth_service.getUserFromAccessToken(expired_access_token, refresh_token),
    )

    assert user == sample_user
    assert fake_user_service == [sample_user.sub]


def test_get_user_from_invalid_access_token_does_not_use_refresh_token(
    auth_service,
    fake_user_service,
    token_data,
):
    access_token_signed_with_wrong_secret = auth_service._encodeRefreshToken(
        token_data,
        timedelta(days=1),
    )
    refresh_token = auth_service._encodeRefreshToken(token_data, timedelta(days=1))

    with pytest.raises(CredentialException):
        asyncio.run(
            auth_service.getUserFromAccessToken(
                access_token_signed_with_wrong_secret,
                refresh_token,
            ),
        )

    assert fake_user_service == []


def test_access_token_without_subject_does_not_use_refresh_token(
    auth_service,
    fake_user_service,
):
    token_without_subject = jwt.encode(
        {"email": "user@example.com"},
        config.AUTHENTICATION_SECRET_KEY,
        algorithm=config.AUTHENTICATION_ALGORITHM,
    )

    with pytest.raises(CredentialException):
        asyncio.run(
            auth_service.getUserFromAccessToken(
                token_without_subject,
                refreshToken="unused-refresh-token",
            ),
        )

    assert fake_user_service == []
