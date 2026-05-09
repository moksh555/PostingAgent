import asyncio
from datetime import UTC, datetime, timedelta

import jwt
import pytest

import app.services.authenticationService as auth_module
from app.errorsHandler.loginError import NotAuthorized
from app.errorsHandler.tokenError import CredentialException
from app.models.tokenModel import TokenModel
from app.models.userModel import UserModel
from app.services.authenticationService import AuthenticationService
from configurations.config import config


def _service() -> AuthenticationService:
    return AuthenticationService(db=object())


def _token_data() -> TokenModel:
    return TokenModel(sub="user-123", email="user@example.com")


def _user_model(sub: str = "user-123") -> UserModel:
    return UserModel(
        email="user@example.com",
        sub=sub,
        userFirstName="Ada",
        userLastName="Lovelace",
        phoneNumber="+1 555 123 4567",
        dateOfBirth=datetime(1990, 1, 1, tzinfo=UTC),
        createdAt=datetime(2025, 1, 1, tzinfo=UTC),
        isActive=True,
        subscriptionType="free",
    )


def _encode_refresh_claims(claims: dict[str, object]) -> str:
    return jwt.encode(
        claims,
        config.AUTHENTICATION_REFRESH_SECRET_KEY,
        algorithm=config.AUTHENTICATION_ALGORITHM,
    )


def test_refresh_token_generates_access_token_signed_with_access_secret() -> None:
    service = _service()
    refresh_token = service._encodeRefreshToken(_token_data(), timedelta(minutes=5))

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


def test_expired_refresh_token_is_rejected_as_not_authorized() -> None:
    service = _service()
    expired_refresh_token = service._encodeRefreshToken(
        _token_data(), timedelta(seconds=-1)
    )

    with pytest.raises(NotAuthorized, match="Refresh token expired"):
        service.generateAccessTokenFromRefreshToken(expired_refresh_token)


@pytest.mark.parametrize(
    "claims",
    [
        {"email": "user@example.com"},
        {"sub": "user-123"},
    ],
)
def test_refresh_token_requires_subject_and_email_claims(
    claims: dict[str, object]
) -> None:
    claims["exp"] = datetime.now(UTC) + timedelta(minutes=5)
    malformed_refresh_token = _encode_refresh_claims(claims)

    with pytest.raises(CredentialException):
        _service().generateAccessTokenFromRefreshToken(malformed_refresh_token)


def test_get_user_from_access_token_refreshes_only_expired_access_token(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    class FakeUserService:
        requested_ids: list[str] = []

        def __init__(self, db: object) -> None:
            self.db = db

        async def getUserFromUserId(self, user_id: str) -> UserModel:
            type(self).requested_ids.append(user_id)
            return _user_model(user_id)

    monkeypatch.setattr(auth_module, "UserService", FakeUserService)
    service = _service()
    expired_access_token = service._encodeAccessToken(
        _token_data(), timedelta(seconds=-1)
    )
    refresh_token = service._encodeRefreshToken(_token_data(), timedelta(minutes=5))

    user = asyncio.run(
        service.getUserFromAccessToken(expired_access_token, refresh_token)
    )

    assert user.sub == "user-123"
    assert FakeUserService.requested_ids == ["user-123"]


def test_get_user_from_access_token_does_not_refresh_invalid_access_token(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    service = _service()
    invalid_access_token = jwt.encode(
        {"sub": "user-123", "email": "user@example.com"},
        "wrong-secret-with-32-bytes-minimum",
        algorithm=config.AUTHENTICATION_ALGORITHM,
    )

    def fail_if_refreshed(refresh_token: str) -> object:
        raise AssertionError("invalid access tokens must not trigger refresh")

    monkeypatch.setattr(service, "generateAccessTokenFromRefreshToken", fail_if_refreshed)

    with pytest.raises(CredentialException):
        asyncio.run(
            service.getUserFromAccessToken(invalid_access_token, "unused-refresh")
        )
