import asyncio
from datetime import datetime, timedelta, timezone

import jwt
import pytest

from app.errorsHandler.loginError import NotAuthorized
from app.errorsHandler.tokenError import CredentialException
from app.models.tokenModel import TokenModel
from app.models.userModel import UserModel
from app.services import authenticationService as auth_module
from app.services.authenticationService import AuthenticationService
from configurations.config import config


def _user(sub: str = "user-123") -> UserModel:
    return UserModel(
        email="person@example.com",
        sub=sub,
        userFirstName="Test",
        userLastName="User",
        phoneNumber="+15555550123",
        dateOfBirth=datetime(1990, 1, 1, tzinfo=timezone.utc),
        createdAt=datetime(2026, 1, 1, tzinfo=timezone.utc),
        isActive=True,
        subscriptionType="free",
    )


def _token_data(sub: str = "user-123") -> TokenModel:
    return TokenModel(sub=sub, email="person@example.com")


@pytest.fixture
def auth_service() -> AuthenticationService:
    return AuthenticationService(db=object())


def test_refresh_endpoint_rejects_access_token_signed_with_access_secret(
    auth_service: AuthenticationService,
):
    access_token = auth_service._encodeAccessToken(
        _token_data(),
        timedelta(minutes=5),
    )

    with pytest.raises(CredentialException):
        auth_service.generateAccessTokenFromRefreshToken(access_token)


def test_expired_refresh_token_is_not_exchanged_for_access_token(
    auth_service: AuthenticationService,
):
    expired_refresh_token = auth_service._encodeRefreshToken(
        _token_data(),
        timedelta(seconds=-1),
    )

    with pytest.raises(NotAuthorized, match="Refresh token expired"):
        auth_service.generateAccessTokenFromRefreshToken(expired_refresh_token)


def test_refresh_token_without_subject_is_rejected(auth_service: AuthenticationService):
    refresh_without_subject = jwt.encode(
        {
            "email": "person@example.com",
            "exp": datetime.now(timezone.utc) + timedelta(minutes=5),
        },
        config.AUTHENTICATION_REFRESH_SECRET_KEY,
        algorithm=config.AUTHENTICATION_ALGORITHM,
    )

    with pytest.raises(CredentialException):
        auth_service.generateAccessTokenFromRefreshToken(refresh_without_subject)


def test_expired_access_token_uses_refresh_token_then_loads_user(
    auth_service: AuthenticationService,
    monkeypatch: pytest.MonkeyPatch,
):
    calls: list[str] = []

    class FakeUserService:
        def __init__(self, db):
            self.db = db

        async def getUserFromUserId(self, user_id: str) -> UserModel:
            calls.append(user_id)
            return _user(sub=user_id)

    monkeypatch.setattr(auth_module, "UserService", FakeUserService)

    expired_access_token = auth_service._encodeAccessToken(
        _token_data(),
        timedelta(seconds=-1),
    )
    refresh_token = auth_service._encodeRefreshToken(
        _token_data(),
        timedelta(minutes=5),
    )

    result = asyncio.run(
        auth_service.getUserFromAccessToken(expired_access_token, refresh_token)
    )

    assert result.sub == "user-123"
    assert calls == ["user-123"]


def test_invalid_access_token_does_not_attempt_refresh(
    auth_service: AuthenticationService,
    monkeypatch: pytest.MonkeyPatch,
):
    def fail_if_refreshed(refresh_token: str):  # pragma: no cover - assertion helper
        raise AssertionError(f"refresh should not be attempted: {refresh_token}")

    monkeypatch.setattr(
        auth_service,
        "generateAccessTokenFromRefreshToken",
        fail_if_refreshed,
    )
    access_token_signed_with_refresh_secret = auth_service._encodeRefreshToken(
        _token_data(),
        timedelta(minutes=5),
    )

    with pytest.raises(CredentialException):
        asyncio.run(
            auth_service.getUserFromAccessToken(
                access_token_signed_with_refresh_secret,
                "unused-refresh-token",
            )
        )
