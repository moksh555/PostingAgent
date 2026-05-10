import asyncio
from datetime import UTC, datetime, timedelta

import jwt  # type: ignore
import pytest

from app.errorsHandler.tokenError import CredentialException
from app.models.tokenModel import RefreshRequest, Token, TokenModel
from app.models.userModel import UserModel
from app.services import authenticationService as auth_module
from configurations.config import config


def _user(user_id: str) -> UserModel:
    return UserModel(
        email="user@example.com",
        sub=user_id,
        userFirstName="test",
        userLastName="user",
        phoneNumber="12345678",
        dateOfBirth=datetime(2000, 1, 1, tzinfo=UTC),
        createdAt=datetime(2026, 1, 1, tzinfo=UTC),
        isActive=True,
        subscriptionType="free",
    )


@pytest.fixture
def auth_service():
    return auth_module.AuthenticationService(db=object())


class TestRefreshTokenExchange:
    def test_valid_refresh_token_mints_access_token_with_same_identity(
        self,
        auth_service,
    ):
        identity = TokenModel(sub="user-123", email="user@example.com")
        refresh_token = auth_service._encodeRefreshToken(identity, timedelta(days=1))

        access_token = auth_service.generateAccessTokenFromRefreshToken(refresh_token)

        assert access_token.tokenType == "ACCESS_TOKEN"
        payload = jwt.decode(
            access_token.accessToken,
            config.AUTHENTICATION_SECRET_KEY,
            algorithms=[config.AUTHENTICATION_ALGORITHM],
        )
        assert payload["sub"] == "user-123"
        assert payload["email"] == "user@example.com"

    def test_access_token_cannot_be_used_as_refresh_token(self, auth_service):
        identity = TokenModel(sub="user-123", email="user@example.com")
        access_token = auth_service._encodeAccessToken(identity, timedelta(minutes=1))

        with pytest.raises(CredentialException):
            auth_service.generateAccessTokenFromRefreshToken(access_token)


class TestGetUserFromAccessToken:
    def test_expired_access_token_refreshes_and_loads_user(
        self,
        auth_service,
        monkeypatch,
    ):
        identity = TokenModel(sub="user-123", email="user@example.com")
        expired_access_token = auth_service._encodeAccessToken(
            identity,
            timedelta(minutes=-1),
        )
        refresh_token = auth_service._encodeRefreshToken(identity, timedelta(days=1))
        loaded_user_ids: list[str] = []

        class FakeUserService:
            def __init__(self, db):
                self.db = db

            async def getUserFromUserId(self, user_id: str) -> UserModel:
                loaded_user_ids.append(user_id)
                return _user(user_id)

        monkeypatch.setattr(auth_module, "UserService", FakeUserService)

        user = asyncio.run(
            auth_service.getUserFromAccessToken(expired_access_token, refresh_token),
        )

        assert user.sub == "user-123"
        assert loaded_user_ids == ["user-123"]

    def test_invalid_access_token_does_not_attempt_refresh(
        self,
        auth_service,
        monkeypatch,
    ):
        def fail_if_refresh_is_called(refresh_token: str) -> Token:
            raise AssertionError(
                f"Refresh should not be attempted for {refresh_token!r}",
            )

        monkeypatch.setattr(
            auth_service,
            "generateAccessTokenFromRefreshToken",
            fail_if_refresh_is_called,
        )

        with pytest.raises(CredentialException):
            asyncio.run(
                auth_service.getUserFromAccessToken(
                    "not-a-jwt",
                    "refresh-token-should-not-be-used",
                ),
            )


class TestRefreshEndpoint:
    def test_cookie_refresh_token_takes_precedence_over_body_token(self):
        from app.api.version1.refresh import refresh

        class FakeAuth:
            def __init__(self):
                self.seen_refresh_tokens: list[str] = []

            def generateAccessTokenFromRefreshToken(self, refresh_token: str) -> Token:
                self.seen_refresh_tokens.append(refresh_token)
                return Token(
                    accessToken=f"access-for-{refresh_token}",
                    tokenType="ACCESS_TOKEN",
                )

        auth = FakeAuth()

        result = asyncio.run(
            refresh(
                auth=auth,
                refresh_token_cookie="cookie-token",
                body=RefreshRequest(refresh_token="body-token"),
            ),
        )

        assert result == Token(
            accessToken="access-for-cookie-token",
            tokenType="ACCESS_TOKEN",
        )
        assert auth.seen_refresh_tokens == ["cookie-token"]

    def test_missing_cookie_and_body_token_is_rejected(self):
        from app.api.version1.refresh import refresh

        with pytest.raises(CredentialException, match="No Refresh Token provided"):
            asyncio.run(refresh(auth=object(), refresh_token_cookie=None, body=None))
