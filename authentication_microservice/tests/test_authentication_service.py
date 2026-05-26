import asyncio
from datetime import UTC, datetime, timedelta
from unittest.mock import Mock

import pytest

from app.errorsHandler.loginError import NotAuthorized
from app.errorsHandler.tokenError import CredentialException
from app.models.tokenModel import TokenModel
from app.models.userModel import UserModel
from app.services import authenticationService as auth_module
from app.services.authenticationService import AuthenticationService


def _user(user_id: str = "user-123", email: str = "user@example.com") -> UserModel:
    return UserModel(
        email=email,
        sub=user_id,
        userFirstName="Test",
        userLastName="User",
        phoneNumber="5551234567",
        dateOfBirth=datetime(1990, 1, 1, tzinfo=UTC),
        createdAt=datetime(2024, 1, 1, tzinfo=UTC),
        isActive=True,
        subscriptionType="free",
    )


def _token_data() -> TokenModel:
    return TokenModel(sub="user-123", email="user@example.com")


def test_get_user_from_access_token_refreshes_only_when_access_token_expired(
    monkeypatch,
):
    service = AuthenticationService(db=object())
    calls: list[str] = []

    class FakeUserService:
        def __init__(self, db):
            self.db = db

        async def getUserFromUserId(self, user_id: str) -> UserModel:
            calls.append(user_id)
            return _user(user_id)

    monkeypatch.setattr(auth_module, "UserService", FakeUserService)

    expired_access = service._encodeAccessToken(_token_data(), timedelta(minutes=-1))
    valid_refresh = service._encodeRefreshToken(_token_data(), timedelta(days=1))

    user = asyncio.run(service.getUserFromAccessToken(expired_access, valid_refresh))

    assert user.sub == "user-123"
    assert calls == ["user-123"]


def test_get_user_from_access_token_does_not_refresh_invalid_access_token(monkeypatch):
    service = AuthenticationService(db=object())
    valid_refresh = service._encodeRefreshToken(_token_data(), timedelta(days=1))
    refresh_spy = Mock(wraps=service.generateAccessTokenFromRefreshToken)
    monkeypatch.setattr(service, "generateAccessTokenFromRefreshToken", refresh_spy)

    with pytest.raises(CredentialException):
        asyncio.run(service.getUserFromAccessToken("not-a-jwt", valid_refresh))

    refresh_spy.assert_not_called()


def test_expired_refresh_token_is_rejected():
    service = AuthenticationService(db=object())
    expired_refresh = service._encodeRefreshToken(_token_data(), timedelta(days=-1))

    with pytest.raises(NotAuthorized, match="Refresh token expired"):
        service.generateAccessTokenFromRefreshToken(expired_refresh)


def test_refresh_token_missing_user_id_is_rejected():
    service = AuthenticationService(db=object())
    refresh_without_sub = service._encodeRefreshToken(
        TokenModel(sub="user-123", email="user@example.com"),
        timedelta(days=1),
    )

    # Re-encode with the refresh secret but remove the required user id claim.
    import jwt
    from configurations.config import config

    payload = jwt.decode(
        refresh_without_sub,
        config.AUTHENTICATION_REFRESH_SECRET_KEY,
        algorithms=[config.AUTHENTICATION_ALGORITHM],
    )
    payload.pop("sub")
    missing_sub_token = jwt.encode(
        payload,
        config.AUTHENTICATION_REFRESH_SECRET_KEY,
        algorithm=config.AUTHENTICATION_ALGORITHM,
    )

    with pytest.raises(CredentialException):
        service.generateAccessTokenFromRefreshToken(missing_sub_token)
