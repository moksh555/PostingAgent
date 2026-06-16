import asyncio
from datetime import datetime, timedelta

import jwt  # type: ignore
import pytest

from app.api.version1.getUserFromToken import getUserFromToken
from app.errorsHandler.loginError import NotAuthorized
from app.errorsHandler.tokenError import CredentialException
from app.models.tokenModel import TokenModel
from app.models.userModel import UserModel
from app.services import authenticationService as auth_module
from app.services.authenticationService import AuthenticationService
from configurations.config import config


def run(coro):
    return asyncio.run(coro)


def sampleUser(sub: str = "user-123") -> UserModel:
    return UserModel(
        email="person@example.com",
        sub=sub,
        userFirstName="Person",
        userLastName="Example",
        phoneNumber="+15555550123",
        dateOfBirth=datetime(1990, 1, 1),
        createdAt=datetime(2026, 1, 1, 12, 0),
        isActive=True,
        subscriptionType="free",
    )


class TestGetUserFromTokenRoute:
    def test_requiresAccessAndRefreshCookies(self):
        with pytest.raises(NotAuthorized, match="No Access Token"):
            run(getUserFromToken(access_token=None, refresh_token="refresh-token"))

        with pytest.raises(NotAuthorized, match="No Refresh Token"):
            run(getUserFromToken(access_token="access-token", refresh_token=None))

    def test_delegatesCookieValuesToAuthService(self):
        expected = sampleUser()

        class FakeAuth:
            def __init__(self):
                self.calls = []

            async def getUserFromAccessToken(self, accessToken, refreshToken):
                self.calls.append((accessToken, refreshToken))
                return expected

        auth = FakeAuth()

        result = run(
            getUserFromToken(
                access_token="cookie-access",
                refresh_token="cookie-refresh",
                auth=auth,
            )
        )

        assert result == expected
        assert auth.calls == [("cookie-access", "cookie-refresh")]


class TestAuthenticationServiceRefreshFallback:
    def test_expiredAccessTokenUsesRefreshToken(self, monkeypatch):
        service = AuthenticationService(db=object())
        user = sampleUser(sub="refresh-user")
        token_data = TokenModel(sub=user.sub, email=user.email)
        expired_access = service._encodeAccessToken(
            token_data,
            timedelta(seconds=-1),
        )
        valid_refresh = service._encodeRefreshToken(
            token_data,
            timedelta(days=1),
        )
        loaded_user_ids = []

        class FakeUserService:
            def __init__(self, db):
                self.db = db

            async def getUserFromUserId(self, user_id: str):
                loaded_user_ids.append(user_id)
                return user

        monkeypatch.setattr(auth_module, "UserService", FakeUserService)

        result = run(service.getUserFromAccessToken(expired_access, valid_refresh))

        assert result == user
        assert loaded_user_ids == [user.sub]

    def test_invalidAccessTokenDoesNotRefresh(self, monkeypatch):
        service = AuthenticationService(db=object())
        token_data = TokenModel(sub="user-123", email="person@example.com")
        invalid_access = jwt.encode(
            token_data.model_dump(),
            "wrong-access-secret-at-least-32-bytes",
            algorithm=config.AUTHENTICATION_ALGORITHM,
        )
        valid_refresh = service._encodeRefreshToken(
            token_data,
            timedelta(days=1),
        )
        refresh_calls = []

        def fail_if_refreshed(refresh_token):
            refresh_calls.append(refresh_token)
            raise AssertionError("invalid access tokens must not trigger refresh")

        monkeypatch.setattr(
            service,
            "generateAccessTokenFromRefreshToken",
            fail_if_refreshed,
        )

        with pytest.raises(CredentialException):
            run(service.getUserFromAccessToken(invalid_access, valid_refresh))

        assert refresh_calls == []
