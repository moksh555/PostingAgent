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


def _user(sub: str = "user-123") -> UserModel:
    return UserModel(
        email="person@example.com",
        sub=sub,
        userFirstName="person",
        userLastName="example",
        phoneNumber="1234567890",
        dateOfBirth=datetime(1990, 1, 1, tzinfo=UTC),
        createdAt=datetime(2024, 1, 1, tzinfo=UTC),
        isActive=True,
        subscriptionType="free",
    )


def _encode_access(payload: dict, expires_delta: timedelta = timedelta(minutes=30)) -> str:
    claims = {**payload, "exp": datetime.now(UTC) + expires_delta}
    return jwt.encode(
        claims,
        config.AUTHENTICATION_SECRET_KEY,
        algorithm=config.AUTHENTICATION_ALGORITHM,
    )


def _encode_refresh(payload: dict, expires_delta: timedelta = timedelta(days=5)) -> str:
    claims = {**payload, "exp": datetime.now(UTC) + expires_delta}
    return jwt.encode(
        claims,
        config.AUTHENTICATION_REFRESH_SECRET_KEY,
        algorithm=config.AUTHENTICATION_ALGORITHM,
    )


class _FakeUserService:
    lookups: list[str] = []
    user = _user()

    def __init__(self, db: object) -> None:
        self.db = db

    async def getUserFromUserId(self, user_id: str) -> UserModel:
        self.lookups.append(user_id)
        return self.user


@pytest.fixture(autouse=True)
def fake_user_service(monkeypatch: pytest.MonkeyPatch) -> None:
    _FakeUserService.lookups = []
    _FakeUserService.user = _user()
    monkeypatch.setattr(auth_module, "UserService", _FakeUserService)


class TestRefreshTokenGeneration:
    def test_valid_refresh_token_mints_access_token_signed_with_access_secret(self) -> None:
        service = AuthenticationService(db=object())
        refresh_token = service._encodeRefreshToken(
            TokenModel(sub="user-123", email="person@example.com"),
            timedelta(days=1),
        )

        token = service.generateAccessTokenFromRefreshToken(refresh_token)

        assert token.tokenType == "ACCESS_TOKEN"
        decoded = jwt.decode(
            token.accessToken,
            config.AUTHENTICATION_SECRET_KEY,
            algorithms=[config.AUTHENTICATION_ALGORITHM],
        )
        assert decoded["sub"] == "user-123"
        assert decoded["email"] == "person@example.com"

        with pytest.raises(jwt.InvalidTokenError):
            jwt.decode(
                token.accessToken,
                config.AUTHENTICATION_REFRESH_SECRET_KEY,
                algorithms=[config.AUTHENTICATION_ALGORITHM],
            )

    def test_access_token_cannot_be_used_as_refresh_token(self) -> None:
        service = AuthenticationService(db=object())
        access_token = service._encodeAccessToken(
            TokenModel(sub="user-123", email="person@example.com"),
            timedelta(minutes=30),
        )

        with pytest.raises(CredentialException):
            service.generateAccessTokenFromRefreshToken(access_token)

    @pytest.mark.parametrize(
        ("refresh_token", "expected_error"),
        [
            (
                _encode_refresh(
                    {"sub": "user-123", "email": "person@example.com"},
                    timedelta(seconds=-1),
                ),
                NotAuthorized,
            ),
            (
                _encode_refresh({"email": "person@example.com"}),
                CredentialException,
            ),
            ("", CredentialException),
        ],
    )
    def test_invalid_refresh_tokens_are_rejected(
        self,
        refresh_token: str,
        expected_error: type[Exception],
    ) -> None:
        service = AuthenticationService(db=object())

        with pytest.raises(expected_error):
            service.generateAccessTokenFromRefreshToken(refresh_token)


class TestGetUserFromAccessToken:
    def test_valid_access_token_loads_user_directly(self) -> None:
        service = AuthenticationService(db=object())
        access_token = _encode_access(
            {"sub": "user-123", "email": "person@example.com"},
        )

        user = asyncio.run(
            service.getUserFromAccessToken(access_token, refreshToken="unused"),
        )

        assert user == _FakeUserService.user
        assert _FakeUserService.lookups == ["user-123"]

    def test_expired_access_token_uses_refresh_token_then_loads_user(self) -> None:
        service = AuthenticationService(db=object())
        expired_access_token = _encode_access(
            {"sub": "user-123", "email": "person@example.com"},
            timedelta(seconds=-1),
        )
        refresh_token = _encode_refresh(
            {"sub": "user-123", "email": "person@example.com"},
        )

        user = asyncio.run(
            service.getUserFromAccessToken(expired_access_token, refresh_token),
        )

        assert user == _FakeUserService.user
        assert _FakeUserService.lookups == ["user-123"]

    def test_malformed_access_token_does_not_attempt_refresh(
        self,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        service = AuthenticationService(db=object())

        def fail_refresh(refresh_token: str) -> None:
            raise AssertionError("refresh should only be attempted for expired access tokens")

        monkeypatch.setattr(service, "generateAccessTokenFromRefreshToken", fail_refresh)

        with pytest.raises(CredentialException):
            asyncio.run(
                service.getUserFromAccessToken("not-a-jwt", refreshToken="refresh-token"),
            )

        assert _FakeUserService.lookups == []
