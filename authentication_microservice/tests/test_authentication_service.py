import asyncio
from datetime import UTC, datetime, timedelta

import jwt  # type: ignore
import pytest
from jwt.exceptions import InvalidTokenError  # type: ignore

from app.errorsHandler.loginError import NotAuthorized
from app.errorsHandler.tokenError import CredentialException
from app.errorsHandler.userError import NoEmailError
from app.models.loginModel import LoginRequest
from app.models.tokenModel import TokenModel
from app.models.userModel import UserPrivateModel
from app.services import authenticationService as auth_module
from configurations.config import config


def test_refresh_exchange_rejects_access_token(auth_service):
    data = TokenModel(sub="user-123", email="user@example.com")
    access_token = auth_service._encodeAccessToken(data, timedelta(minutes=5))

    with pytest.raises(CredentialException):
        auth_service.generateAccessTokenFromRefreshToken(access_token)


def test_refresh_exchange_returns_access_token_signed_with_access_secret(auth_service):
    data = TokenModel(sub="user-123", email="user@example.com")
    refresh_token = auth_service._encodeRefreshToken(data, timedelta(days=1))

    token = auth_service.generateAccessTokenFromRefreshToken(refresh_token)

    assert token.tokenType == "ACCESS_TOKEN"
    payload = jwt.decode(
        token.accessToken,
        config.AUTHENTICATION_SECRET_KEY,
        algorithms=[config.AUTHENTICATION_ALGORITHM],
    )
    assert payload["sub"] == "user-123"
    assert payload["email"] == "user@example.com"
    with pytest.raises(InvalidTokenError):
        jwt.decode(
            token.accessToken,
            config.AUTHENTICATION_REFRESH_SECRET_KEY,
            algorithms=[config.AUTHENTICATION_ALGORITHM],
        )


def test_refresh_exchange_rejects_token_without_subject(auth_service):
    refresh_token = jwt.encode(
        {
            "email": "user@example.com",
            "exp": datetime.now(UTC) + timedelta(days=1),
        },
        config.AUTHENTICATION_REFRESH_SECRET_KEY,
        algorithm=config.AUTHENTICATION_ALGORITHM,
    )

    with pytest.raises(CredentialException):
        auth_service.generateAccessTokenFromRefreshToken(refresh_token)


def test_get_user_from_access_token_refreshes_only_after_expiry(
    auth_service,
    monkeypatch,
    user_model_factory,
):
    lookups: list[str] = []

    class FakeUserService:
        def __init__(self, db):
            self.db = db

        async def getUserFromUserId(self, user_id: str):
            lookups.append(user_id)
            return user_model_factory(sub=user_id)

    monkeypatch.setattr(auth_module, "UserService", FakeUserService)
    data = TokenModel(sub="user-123", email="user@example.com")
    expired_access = auth_service._encodeAccessToken(data, timedelta(seconds=-1))
    refresh_token = auth_service._encodeRefreshToken(data, timedelta(days=1))

    user = asyncio.run(
        auth_service.getUserFromAccessToken(expired_access, refresh_token)
    )

    assert user.sub == "user-123"
    assert lookups == ["user-123"]


def test_get_user_from_access_token_does_not_refresh_invalid_access_token(
    auth_service,
    monkeypatch,
):
    lookups: list[str] = []

    class FakeUserService:
        def __init__(self, db):
            self.db = db

        async def getUserFromUserId(self, user_id: str):
            lookups.append(user_id)
            raise AssertionError("invalid access tokens must not load users")

    def fail_if_refreshed(refresh_token: str):
        raise AssertionError("invalid access tokens must not trigger refresh")

    monkeypatch.setattr(auth_module, "UserService", FakeUserService)
    monkeypatch.setattr(
        auth_service,
        "generateAccessTokenFromRefreshToken",
        fail_if_refreshed,
    )
    data = TokenModel(sub="user-123", email="user@example.com")
    wrong_secret_token = auth_service._encodeRefreshToken(data, timedelta(days=1))

    with pytest.raises(CredentialException):
        asyncio.run(
            auth_service.getUserFromAccessToken(
                wrong_secret_token,
                refreshToken="unused-refresh-token",
            )
        )
    assert lookups == []


def test_login_normalizes_email_and_uses_private_user_lookup(
    auth_service,
    monkeypatch,
):
    calls: list[tuple[str, bool]] = []

    class FakeUserService:
        def __init__(self, db):
            self.db = db

        async def getUserFromEmail(self, email: str, private: bool = False):
            calls.append((email, private))
            return UserPrivateModel(
                email=email,
                sub="user-123",
                userFirstName="jane",
                userLastName="doe",
                phoneNumber="+15551234567",
                dateOfBirth=datetime(1990, 1, 1, tzinfo=UTC),
                createdAt=datetime(2026, 1, 1, tzinfo=UTC),
                isActive=True,
                subscriptionType="free",
                passwordHash="hashed",
            )

        def _comparePassword(self, password: str, passwordHash: str) -> bool:
            return password == "CorrectPass1!"

    monkeypatch.setattr(auth_module, "UserService", FakeUserService)

    access_token, refresh_token = asyncio.run(
        auth_service.loginUser(
            LoginRequest(email="  USER@Example.COM ", password="CorrectPass1!")
        )
    )

    assert calls == [("user@example.com", True)]
    assert access_token.tokenType == "ACCESS_TOKEN"
    assert refresh_token.tokenType == "REFRESH_TOKEN"


def test_login_maps_unknown_email_to_not_authorized(auth_service, monkeypatch):
    class FakeUserService:
        def __init__(self, db):
            self.db = db

        async def getUserFromEmail(self, email: str, private: bool = False):
            raise NoEmailError("missing")

    monkeypatch.setattr(auth_module, "UserService", FakeUserService)

    with pytest.raises(NotAuthorized, match="Invalid email or password"):
        asyncio.run(
            auth_service.loginUser(
                LoginRequest(email="missing@example.com", password="CorrectPass1!")
            )
        )
