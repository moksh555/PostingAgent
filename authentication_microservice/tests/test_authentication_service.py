import asyncio
from datetime import UTC, datetime, timedelta

import jwt  # type: ignore
import pytest

from app.errorsHandler.loginError import NoEmailorPasswordFound, NotAuthorized
from app.errorsHandler.tokenError import CredentialException
from app.errorsHandler.userError import NoEmailError
from app.models.loginModel import LoginRequest
from app.models.tokenModel import TokenModel
from app.models.userModel import UserModel, UserPrivateModel
from app.services import authenticationService as auth_module
from app.services.authenticationService import AuthenticationService
from configurations.config import config


def _user(sub: str = "user-123", email: str = "user@example.com") -> UserModel:
    return UserModel(
        email=email,
        sub=sub,
        userFirstName="ada",
        userLastName="lovelace",
        phoneNumber="15551234567",
        dateOfBirth=datetime(1990, 1, 1, tzinfo=UTC),
        createdAt=datetime(2026, 1, 1, tzinfo=UTC),
        isActive=True,
        subscriptionType="free",
    )


def _private_user(
    sub: str = "user-123",
    email: str = "user@example.com",
    password_hash: str = "stored-hash",
) -> UserPrivateModel:
    public = _user(sub=sub, email=email)
    return UserPrivateModel(**public.model_dump(), passwordHash=password_hash)


def _service() -> AuthenticationService:
    return AuthenticationService(db=object())  # type: ignore[arg-type]


class TestRefreshTokenExchange:
    def test_refresh_tokens_use_separate_key_and_issue_access_token(self):
        service = _service()
        data = TokenModel(sub="user-123", email="user@example.com")

        access_token = service._encodeAccessToken(data, timedelta(minutes=5))
        refresh_token = service._encodeRefreshToken(data, timedelta(days=1))

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

        assert access_payload["sub"] == "user-123"
        assert refresh_payload["sub"] == "user-123"

        with pytest.raises(CredentialException):
            service.generateAccessTokenFromRefreshToken(access_token)

        new_access = service.generateAccessTokenFromRefreshToken(refresh_token)
        new_payload = jwt.decode(
            new_access.accessToken,
            config.AUTHENTICATION_SECRET_KEY,
            algorithms=[config.AUTHENTICATION_ALGORITHM],
        )
        assert new_access.tokenType == "ACCESS_TOKEN"
        assert new_payload["sub"] == "user-123"
        assert new_payload["email"] == "user@example.com"

    def test_expired_refresh_token_is_not_exchanged(self):
        service = _service()
        expired_refresh = service._encodeRefreshToken(
            TokenModel(sub="user-123", email="user@example.com"),
            timedelta(seconds=-1),
        )

        with pytest.raises(NotAuthorized, match="Refresh token expired"):
            service.generateAccessTokenFromRefreshToken(expired_refresh)

    def test_refresh_token_without_subject_is_rejected(self):
        service = _service()
        malformed_refresh = jwt.encode(
            {
                "email": "user@example.com",
                "exp": datetime.now(UTC) + timedelta(days=1),
            },
            config.AUTHENTICATION_REFRESH_SECRET_KEY,
            algorithm=config.AUTHENTICATION_ALGORITHM,
        )

        with pytest.raises(CredentialException):
            service.generateAccessTokenFromRefreshToken(malformed_refresh)


class TestAccessTokenLookup:
    def test_expired_access_token_refreshes_once_then_loads_user(
        self,
        monkeypatch,
    ):
        expected_user = _user()
        looked_up_ids: list[str] = []

        class FakeUserService:
            def __init__(self, db):
                self.db = db

            async def getUserFromUserId(self, user_id: str) -> UserModel:
                looked_up_ids.append(user_id)
                return expected_user

        monkeypatch.setattr(auth_module, "UserService", FakeUserService)
        service = _service()
        expired_access = service._encodeAccessToken(
            TokenModel(sub=expected_user.sub, email=expected_user.email),
            timedelta(seconds=-1),
        )
        refresh_token = service._encodeRefreshToken(
            TokenModel(sub=expected_user.sub, email=expected_user.email),
            timedelta(days=1),
        )

        result = asyncio.run(
            service.getUserFromAccessToken(expired_access, refresh_token),
        )

        assert result == expected_user
        assert looked_up_ids == [expected_user.sub]

    def test_invalid_access_token_does_not_attempt_refresh_or_user_lookup(
        self,
        monkeypatch,
    ):
        class FailingUserService:
            def __init__(self, db):
                self.db = db

            async def getUserFromUserId(self, user_id: str) -> UserModel:
                raise AssertionError("invalid access token should not load a user")

        def fail_refresh(refresh_token: str):
            raise AssertionError("invalid access token should not refresh")

        monkeypatch.setattr(auth_module, "UserService", FailingUserService)
        service = _service()
        monkeypatch.setattr(service, "generateAccessTokenFromRefreshToken", fail_refresh)
        refresh_signed_token = service._encodeRefreshToken(
            TokenModel(sub="user-123", email="user@example.com"),
            timedelta(days=1),
        )

        with pytest.raises(CredentialException):
            asyncio.run(
                service.getUserFromAccessToken(
                    refresh_signed_token,
                    refresh_signed_token,
                ),
            )


class TestLoginCredentialMapping:
    def test_missing_email_or_password_fails_before_lookup(self):
        service = _service()

        with pytest.raises(NoEmailorPasswordFound, match="valid email"):
            asyncio.run(service.authenticateUser("", "Password1!"))

        with pytest.raises(NoEmailorPasswordFound, match="valid password"):
            asyncio.run(service.authenticateUser("user@example.com", ""))

    def test_unknown_email_maps_to_generic_not_authorized(self, monkeypatch):
        class FakeUserService:
            def __init__(self, db):
                self.db = db

            async def getUserFromEmail(self, email: str, private: bool = False):
                raise NoEmailError("not found")

        monkeypatch.setattr(auth_module, "UserService", FakeUserService)

        with pytest.raises(NotAuthorized, match="Invalid email or password"):
            asyncio.run(_service().authenticateUser("user@example.com", "Password1!"))

    def test_wrong_password_is_not_authorized(self, monkeypatch):
        class FakeUserService:
            def __init__(self, db):
                self.db = db

            async def getUserFromEmail(
                self,
                email: str,
                private: bool = False,
            ) -> UserPrivateModel:
                assert private is True
                return _private_user(email=email)

            def _comparePassword(self, password: str, password_hash: str) -> bool:
                return False

        monkeypatch.setattr(auth_module, "UserService", FakeUserService)

        with pytest.raises(NotAuthorized, match="Invalid password"):
            asyncio.run(_service().authenticateUser("user@example.com", "wrong"))

    def test_login_user_normalizes_email_before_authentication(self, monkeypatch):
        seen_credentials: list[tuple[str, str]] = []

        async def fake_authenticate(self, email: str, password: str):
            seen_credentials.append((email, password))
            return (
                auth_module.Token(accessToken="access", tokenType="ACCESS_TOKEN"),
                auth_module.Token(accessToken="refresh", tokenType="REFRESH_TOKEN"),
            )

        monkeypatch.setattr(AuthenticationService, "authenticateUser", fake_authenticate)

        asyncio.run(
            _service().loginUser(
                LoginRequest(email="  USER@Example.COM  ", password="Password1!"),
            ),
        )

        assert seen_credentials == [("user@example.com", "Password1!")]
