import asyncio
from datetime import UTC, datetime, timedelta

import jwt
import pytest

from app.errorsHandler.loginError import NoEmailorPasswordFound, NotAuthorized
from app.errorsHandler.tokenError import CredentialException
from app.errorsHandler.userError import NoEmailError
from app.models.tokenModel import TokenModel
from app.models.userModel import UserPrivateModel
from app.services.authenticationService import AuthenticationService
from app.services.userService import UserService
from configurations.config import config


def test_refresh_exchange_rejects_access_token_signed_with_access_secret():
    service = AuthenticationService(db=object())
    token_data = TokenModel(sub="user-123", email="user@example.com")
    access_token = service._encodeAccessToken(token_data, timedelta(minutes=5))

    with pytest.raises(CredentialException):
        service.generateAccessTokenFromRefreshToken(access_token)


def test_refresh_exchange_uses_refresh_secret_and_mints_access_token():
    service = AuthenticationService(db=object())
    token_data = TokenModel(sub="user-123", email="user@example.com")
    refresh_token = service._encodeRefreshToken(token_data, timedelta(days=1))

    new_access_token = service.generateAccessTokenFromRefreshToken(refresh_token)

    assert new_access_token.tokenType == "ACCESS_TOKEN"
    access_payload = jwt.decode(
        new_access_token.accessToken,
        config.AUTHENTICATION_SECRET_KEY,
        algorithms=[config.AUTHENTICATION_ALGORITHM],
    )
    assert access_payload["sub"] == "user-123"
    with pytest.raises(jwt.InvalidTokenError):
        jwt.decode(
            new_access_token.accessToken,
            config.AUTHENTICATION_REFRESH_SECRET_KEY,
            algorithms=[config.AUTHENTICATION_ALGORITHM],
        )


def test_refresh_exchange_rejects_expired_refresh_token():
    service = AuthenticationService(db=object())
    token_data = TokenModel(sub="user-123", email="user@example.com")
    expired_refresh_token = service._encodeRefreshToken(
        token_data,
        timedelta(seconds=-1),
    )

    with pytest.raises(NotAuthorized, match="Refresh token expired"):
        service.generateAccessTokenFromRefreshToken(expired_refresh_token)


def test_refresh_exchange_rejects_refresh_token_without_subject():
    service = AuthenticationService(db=object())
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


def test_get_user_from_access_token_returns_user_without_refresh(monkeypatch, sample_user):
    service = AuthenticationService(db=object())
    token_data = TokenModel(sub=sample_user.sub, email=sample_user.email)
    access_token = service._encodeAccessToken(token_data, timedelta(minutes=5))
    looked_up_user_ids: list[str] = []

    async def fake_get_user_from_user_id(self, user_id: str):
        looked_up_user_ids.append(user_id)
        return sample_user

    monkeypatch.setattr(
        UserService,
        "getUserFromUserId",
        fake_get_user_from_user_id,
    )

    user = asyncio.run(
        service.getUserFromAccessToken(access_token, refreshToken="unused-refresh"),
    )

    assert user == sample_user
    assert looked_up_user_ids == [sample_user.sub]


def test_get_user_from_expired_access_token_refreshes_once(monkeypatch, sample_user):
    service = AuthenticationService(db=object())
    token_data = TokenModel(sub=sample_user.sub, email=sample_user.email)
    expired_access_token = service._encodeAccessToken(token_data, timedelta(seconds=-1))
    refresh_token = service._encodeRefreshToken(token_data, timedelta(days=1))
    looked_up_user_ids: list[str] = []

    async def fake_get_user_from_user_id(self, user_id: str):
        looked_up_user_ids.append(user_id)
        return sample_user

    monkeypatch.setattr(
        UserService,
        "getUserFromUserId",
        fake_get_user_from_user_id,
    )

    user = asyncio.run(
        service.getUserFromAccessToken(expired_access_token, refresh_token),
    )

    assert user == sample_user
    assert looked_up_user_ids == [sample_user.sub]


def test_invalid_access_token_does_not_attempt_refresh(monkeypatch):
    service = AuthenticationService(db=object())
    invalid_access_token = jwt.encode(
        {
            "sub": "user-123",
            "email": "user@example.com",
            "exp": datetime.now(UTC) + timedelta(minutes=5),
        },
        "wrong-access-secret",
        algorithm=config.AUTHENTICATION_ALGORITHM,
    )

    def fail_refresh(_refresh_token: str):
        raise AssertionError("invalid access tokens must not be refreshed")

    async def fail_user_lookup(self, _user_id: str):
        raise AssertionError("invalid access tokens must not load users")

    monkeypatch.setattr(service, "generateAccessTokenFromRefreshToken", fail_refresh)
    monkeypatch.setattr(UserService, "getUserFromUserId", fail_user_lookup)

    with pytest.raises(CredentialException):
        asyncio.run(
            service.getUserFromAccessToken(invalid_access_token, "refresh-token"),
        )


def test_authenticate_user_maps_unknown_email_to_generic_unauthorized(monkeypatch):
    service = AuthenticationService(db=object())

    async def fake_get_user_from_email(self, _email: str, private: bool = False):
        raise NoEmailError("missing")

    monkeypatch.setattr(UserService, "getUserFromEmail", fake_get_user_from_email)

    with pytest.raises(NotAuthorized, match="Invalid email or password"):
        asyncio.run(service.authenticateUser("missing@example.com", "Password1!"))


def test_authenticate_user_rejects_wrong_password(monkeypatch):
    service = AuthenticationService(db=object())
    private_user = UserPrivateModel(
        email="user@example.com",
        sub="user-123",
        userFirstName="test",
        userLastName="user",
        phoneNumber="+15551234567",
        dateOfBirth=datetime(1990, 1, 1, tzinfo=UTC),
        createdAt=datetime(2026, 1, 1, tzinfo=UTC),
        isActive=True,
        subscriptionType="free",
        passwordHash="stored-hash",
    )

    async def fake_get_user_from_email(self, _email: str, private: bool = False):
        assert private is True
        return private_user

    monkeypatch.setattr(UserService, "getUserFromEmail", fake_get_user_from_email)
    monkeypatch.setattr(UserService, "_comparePassword", lambda *_args: False)

    with pytest.raises(NotAuthorized, match="Invalid password"):
        asyncio.run(service.authenticateUser("user@example.com", "WrongPassword1!"))


@pytest.mark.parametrize(
    ("email", "password", "expected_message"),
    [
        ("", "Password1!", "Please enter valid email"),
        ("user@example.com", "", "Please enter valid password"),
    ],
)
def test_authenticate_user_rejects_missing_credentials(email, password, expected_message):
    service = AuthenticationService(db=object())

    with pytest.raises(NoEmailorPasswordFound, match=expected_message):
        asyncio.run(service.authenticateUser(email, password))
