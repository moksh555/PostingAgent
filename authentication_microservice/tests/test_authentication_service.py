import asyncio
from datetime import UTC, datetime, timedelta

import jwt
import pytest

from app.errorsHandler.loginError import NotAuthorized
from app.errorsHandler.tokenError import CredentialException
from app.models.tokenModel import TokenModel
from app.models.userModel import UserModel
from app.services import authenticationService as auth_module
from app.services.authenticationService import AuthenticationService
from configurations.config import config


def user_model(sub: str = "user-123") -> UserModel:
    return UserModel(
        email="user@example.com",
        sub=sub,
        userFirstName="Ada",
        userLastName="Lovelace",
        phoneNumber="+1 555 123 4567",
        dateOfBirth=datetime(1990, 1, 1, tzinfo=UTC),
        createdAt=datetime(2026, 1, 1, tzinfo=UTC),
        isActive=True,
        subscriptionType="free",
    )


class FakeUserService:
    calls: list[str] = []

    def __init__(self, db):
        self.db = db

    async def getUserFromUserId(self, user_id: str) -> UserModel:
        self.calls.append(user_id)
        return user_model(user_id)


class TestAuthenticationServiceTokens:
    def test_generate_access_token_from_refresh_rejects_missing_subject(self):
        service = AuthenticationService(db=None)
        refresh_token = jwt.encode(
            {
                "email": "user@example.com",
                "exp": datetime.now(UTC) + timedelta(days=1),
            },
            config.AUTHENTICATION_REFRESH_SECRET_KEY,
            algorithm=config.AUTHENTICATION_ALGORITHM,
        )

        with pytest.raises(CredentialException):
            service.generateAccessTokenFromRefreshToken(refresh_token)

    def test_generate_access_token_from_refresh_rejects_expired_refresh_token(self):
        service = AuthenticationService(db=None)
        expired_refresh = service._encodeRefreshToken(
            TokenModel(sub="user-123", email="user@example.com"),
            timedelta(seconds=-1),
        )

        with pytest.raises(NotAuthorized) as exc_info:
            service.generateAccessTokenFromRefreshToken(expired_refresh)

        assert exc_info.value.message == "Refresh token expired"

    def test_generate_access_token_from_refresh_uses_refresh_secret(self):
        service = AuthenticationService(db=None)
        access_token = service._encodeAccessToken(
            TokenModel(sub="user-123", email="user@example.com"),
            timedelta(minutes=5),
        )

        with pytest.raises(CredentialException):
            service.generateAccessTokenFromRefreshToken(access_token)

    def test_get_user_from_access_token_refreshes_only_when_access_token_expired(self, monkeypatch):
        service = AuthenticationService(db=None)
        FakeUserService.calls = []
        monkeypatch.setattr(auth_module, "UserService", FakeUserService)
        token_data = TokenModel(sub="user-123", email="user@example.com")
        expired_access = service._encodeAccessToken(token_data, timedelta(seconds=-1))
        valid_refresh = service._encodeRefreshToken(token_data, timedelta(days=1))

        user = asyncio.run(service.getUserFromAccessToken(expired_access, valid_refresh))

        assert user.sub == "user-123"
        assert FakeUserService.calls == ["user-123"]

    def test_get_user_from_access_token_does_not_refresh_malformed_access_token(self, monkeypatch):
        service = AuthenticationService(db=None)
        monkeypatch.setattr(
            service,
            "generateAccessTokenFromRefreshToken",
            lambda refresh_token: pytest.fail("malformed access tokens must not refresh"),
        )

        with pytest.raises(CredentialException):
            asyncio.run(service.getUserFromAccessToken("not-a-jwt", "refresh-token"))
