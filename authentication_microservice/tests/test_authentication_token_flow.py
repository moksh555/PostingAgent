import asyncio
from datetime import UTC, datetime, timedelta

import jwt
import pytest

from app.errorsHandler.loginError import NotAuthorized
from app.errorsHandler.tokenError import CredentialException
from app.models.tokenModel import Token, TokenModel
from app.models.userModel import UserModel
from app.services import authenticationService as auth_module
from app.services.authenticationService import AuthenticationService
from configurations.config import config


def _auth_service() -> AuthenticationService:
    return AuthenticationService(db=object())


def _identity() -> TokenModel:
    return TokenModel(sub="user-123", email="user@example.com")


def _user(user_id: str = "user-123") -> UserModel:
    return UserModel(
        email="user@example.com",
        sub=user_id,
        userFirstName="Ada",
        userLastName="Lovelace",
        phoneNumber="+1 555 123 4567",
        dateOfBirth=datetime(1990, 1, 1, tzinfo=UTC),
        createdAt=datetime(2025, 1, 1, tzinfo=UTC),
        isActive=True,
        subscriptionType="free",
    )


def test_refresh_token_mints_access_token_with_access_secret() -> None:
    service = _auth_service()
    refresh_token = service._encodeRefreshToken(_identity(), timedelta(minutes=5))

    access_token = service.generateAccessTokenFromRefreshToken(refresh_token)

    assert access_token.tokenType == "ACCESS_TOKEN"
    payload = jwt.decode(
        access_token.accessToken,
        config.AUTHENTICATION_SECRET_KEY,
        algorithms=[config.AUTHENTICATION_ALGORITHM],
    )
    assert payload["sub"] == "user-123"
    assert payload["email"] == "user@example.com"
    with pytest.raises(jwt.InvalidTokenError):
        jwt.decode(
            access_token.accessToken,
            config.AUTHENTICATION_REFRESH_SECRET_KEY,
            algorithms=[config.AUTHENTICATION_ALGORITHM],
        )


def test_access_token_cannot_be_used_as_refresh_token() -> None:
    access_token = _auth_service()._encodeAccessToken(_identity(), timedelta(minutes=5))

    with pytest.raises(CredentialException):
        _auth_service().generateAccessTokenFromRefreshToken(access_token)


def test_expired_refresh_token_is_rejected_as_not_authorized() -> None:
    expired_refresh_token = _auth_service()._encodeRefreshToken(
        _identity(),
        timedelta(seconds=-1),
    )

    with pytest.raises(NotAuthorized, match="Refresh token expired"):
        _auth_service().generateAccessTokenFromRefreshToken(expired_refresh_token)


@pytest.mark.parametrize(
    "claims",
    [
        {"email": "user@example.com"},
        {"sub": "user-123"},
    ],
)
def test_refresh_token_requires_identity_claims(claims: dict[str, object]) -> None:
    claims["exp"] = datetime.now(UTC) + timedelta(minutes=5)
    malformed_refresh_token = jwt.encode(
        claims,
        config.AUTHENTICATION_REFRESH_SECRET_KEY,
        algorithm=config.AUTHENTICATION_ALGORITHM,
    )

    with pytest.raises(CredentialException):
        _auth_service().generateAccessTokenFromRefreshToken(malformed_refresh_token)


def test_expired_access_token_uses_refresh_token_then_loads_user(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    loaded_user_ids: list[str] = []

    class FakeUserService:
        def __init__(self, db: object) -> None:
            self.db = db

        async def getUserFromUserId(self, user_id: str) -> UserModel:
            loaded_user_ids.append(user_id)
            return _user(user_id)

    monkeypatch.setattr(auth_module, "UserService", FakeUserService)
    service = _auth_service()
    expired_access_token = service._encodeAccessToken(
        _identity(),
        timedelta(seconds=-1),
    )
    refresh_token = service._encodeRefreshToken(_identity(), timedelta(minutes=5))

    user = asyncio.run(
        service.getUserFromAccessToken(expired_access_token, refresh_token),
    )

    assert user.sub == "user-123"
    assert loaded_user_ids == ["user-123"]


def test_invalid_access_token_does_not_attempt_refresh(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def fail_if_refreshed(refresh_token: str) -> Token:
        raise AssertionError(f"unexpected refresh for {refresh_token!r}")

    service = _auth_service()
    monkeypatch.setattr(service, "generateAccessTokenFromRefreshToken", fail_if_refreshed)

    with pytest.raises(CredentialException):
        asyncio.run(
            service.getUserFromAccessToken(
                "not-a-jwt",
                "refresh-token-should-not-be-used",
            ),
        )
