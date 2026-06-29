import asyncio
from datetime import UTC, datetime, timedelta

import jwt
import pytest

from app.errorsHandler.loginError import NotAuthorized
from app.errorsHandler.tokenError import CredentialException
from app.models.tokenModel import TokenModel
from app.services.authenticationService import AuthenticationService
from configurations.config import config


def user_row(user_id: str = "user-1") -> dict:
    return {
        "email": "person@example.com",
        "user_id": user_id,
        "first_name": "person",
        "last_name": "example",
        "phone_number": "+15551234567",
        "date_of_birth": datetime(2000, 1, 1, tzinfo=UTC),
        "created_at": datetime(2026, 1, 1, tzinfo=UTC),
        "is_active": True,
        "subscription_type": "free",
        "password_hash": "unused",
    }


class FakeDb:
    def __init__(self, row: dict | None = None) -> None:
        self.row = row or user_row()
        self.fetchrow_calls: list[tuple[str, str]] = []

    async def fetchrow(self, query: str, value: str) -> dict:
        self.fetchrow_calls.append((query, value))
        return self.row


def test_refresh_token_exchange_rejects_access_tokens() -> None:
    service = AuthenticationService(FakeDb())
    access_token = service._encodeAccessToken(
        TokenModel(sub="user-1", email="person@example.com"),
        timedelta(minutes=5),
    )

    with pytest.raises(CredentialException):
        service.generateAccessTokenFromRefreshToken(access_token)


def test_refresh_token_exchange_rejects_missing_subject_claim() -> None:
    service = AuthenticationService(FakeDb())
    refresh_without_sub = jwt.encode(
        {
            "email": "person@example.com",
            "exp": datetime.now(UTC) + timedelta(minutes=5),
        },
        config.AUTHENTICATION_REFRESH_SECRET_KEY,
        algorithm=config.AUTHENTICATION_ALGORITHM,
    )

    with pytest.raises(CredentialException):
        service.generateAccessTokenFromRefreshToken(refresh_without_sub)


def test_refresh_token_exchange_rejects_expired_refresh_tokens() -> None:
    service = AuthenticationService(FakeDb())
    expired_refresh = service._encodeRefreshToken(
        TokenModel(sub="user-1", email="person@example.com"),
        timedelta(minutes=-5),
    )

    with pytest.raises(NotAuthorized, match="Refresh token expired"):
        service.generateAccessTokenFromRefreshToken(expired_refresh)


def test_expired_access_token_uses_refresh_token_before_loading_user() -> None:
    db = FakeDb(user_row("user-1"))
    service = AuthenticationService(db)
    expired_access = service._encodeAccessToken(
        TokenModel(sub="user-1", email="person@example.com"),
        timedelta(minutes=-5),
    )
    valid_refresh = service._encodeRefreshToken(
        TokenModel(sub="user-1", email="person@example.com"),
        timedelta(days=1),
    )

    user = asyncio.run(service.getUserFromAccessToken(expired_access, valid_refresh))

    assert user.sub == "user-1"
    assert db.fetchrow_calls == [("SELECT * FROM users WHERE user_id = $1", "user-1")]


def test_invalid_access_token_does_not_refresh_or_load_user() -> None:
    class RefreshSpy(AuthenticationService):
        def generateAccessTokenFromRefreshToken(self, refreshToken: str):  # noqa: N802
            raise AssertionError("malformed access tokens must not trigger refresh")

    db = FakeDb()
    service = RefreshSpy(db)

    with pytest.raises(CredentialException):
        asyncio.run(service.getUserFromAccessToken("not-a-jwt", "refresh-token"))

    assert db.fetchrow_calls == []
