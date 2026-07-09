import asyncio
from datetime import timedelta
from unittest.mock import Mock

import jwt
import pytest

from app.errorsHandler.loginError import NotAuthorized
from app.errorsHandler.tokenError import CredentialException
from app.models.tokenModel import TokenModel
from configurations.config import config


def _claims() -> TokenModel:
    return TokenModel(sub="user-1", email="user@example.com")


class TestGenerateAccessTokenFromRefreshToken:
    def test_valid_refresh_token_returns_access_token_signed_with_access_secret(
        self,
        auth_service,
    ):
        refresh_token = auth_service._encodeRefreshToken(_claims(), timedelta(minutes=5))

        access_token = auth_service.generateAccessTokenFromRefreshToken(refresh_token)

        decoded = jwt.decode(
            access_token.accessToken,
            config.AUTHENTICATION_SECRET_KEY,
            algorithms=[config.AUTHENTICATION_ALGORITHM],
        )
        assert access_token.tokenType == "ACCESS_TOKEN"
        assert decoded["sub"] == "user-1"
        assert decoded["email"] == "user@example.com"

    def test_access_token_cannot_be_reused_as_refresh_token(self, auth_service):
        access_token = auth_service._encodeAccessToken(_claims(), timedelta(minutes=5))

        with pytest.raises(CredentialException):
            auth_service.generateAccessTokenFromRefreshToken(access_token)

    def test_expired_refresh_token_raises_not_authorized(self, auth_service):
        refresh_token = auth_service._encodeRefreshToken(
            _claims(),
            timedelta(seconds=-1),
        )

        with pytest.raises(NotAuthorized, match="Refresh token expired"):
            auth_service.generateAccessTokenFromRefreshToken(refresh_token)

    def test_refresh_token_without_subject_is_rejected(self, auth_service):
        refresh_token = jwt.encode(
            {"email": "user@example.com"},
            config.AUTHENTICATION_REFRESH_SECRET_KEY,
            algorithm=config.AUTHENTICATION_ALGORITHM,
        )

        with pytest.raises(CredentialException):
            auth_service.generateAccessTokenFromRefreshToken(refresh_token)


class TestGetUserFromAccessToken:
    def _patch_user_service(self, monkeypatch, user_model):
        import app.services.authenticationService as authentication_module

        calls: list[str] = []

        class FakeUserService:
            def __init__(self, db):
                self.db = db

            async def getUserFromUserId(self, user_id: str):
                calls.append(user_id)
                return user_model

        monkeypatch.setattr(authentication_module, "UserService", FakeUserService)
        return calls

    def test_valid_access_token_returns_user_without_refreshing(
        self,
        auth_service,
        monkeypatch,
        user_model,
    ):
        calls = self._patch_user_service(monkeypatch, user_model)
        refresh_spy = Mock(wraps=auth_service.generateAccessTokenFromRefreshToken)
        monkeypatch.setattr(
            auth_service,
            "generateAccessTokenFromRefreshToken",
            refresh_spy,
        )
        access_token = auth_service._encodeAccessToken(_claims(), timedelta(minutes=5))

        result = asyncio.run(
            auth_service.getUserFromAccessToken(access_token, refreshToken="unused"),
        )

        assert result == user_model
        assert calls == ["user-1"]
        refresh_spy.assert_not_called()

    def test_expired_access_token_uses_refresh_token_and_returns_user(
        self,
        auth_service,
        monkeypatch,
        user_model,
    ):
        calls = self._patch_user_service(monkeypatch, user_model)
        access_token = auth_service._encodeAccessToken(_claims(), timedelta(seconds=-1))
        refresh_token = auth_service._encodeRefreshToken(_claims(), timedelta(minutes=5))

        result = asyncio.run(
            auth_service.getUserFromAccessToken(access_token, refresh_token),
        )

        assert result == user_model
        assert calls == ["user-1"]

    def test_invalid_access_token_does_not_attempt_refresh(
        self,
        auth_service,
        monkeypatch,
        user_model,
    ):
        self._patch_user_service(monkeypatch, user_model)
        refresh_spy = Mock(side_effect=AssertionError("refresh should not be attempted"))
        monkeypatch.setattr(
            auth_service,
            "generateAccessTokenFromRefreshToken",
            refresh_spy,
        )
        wrong_secret_token = auth_service._encodeRefreshToken(
            _claims(),
            timedelta(minutes=5),
        )

        with pytest.raises(CredentialException):
            asyncio.run(
                auth_service.getUserFromAccessToken(
                    accessToken=wrong_secret_token,
                    refreshToken="unused",
                ),
            )

        refresh_spy.assert_not_called()
