import asyncio
from datetime import UTC, datetime, timedelta

import jwt  # type: ignore
import pytest

from app.errorsHandler.tokenError import CredentialException
from app.services.authenticationService import AuthenticationService
from configurations.config import config


def run(coro):
    return asyncio.run(coro)


def _jwt(secret: str, exp_delta: timedelta, *, sub: str = "user-123") -> str:
    return jwt.encode(
        {
            "sub": sub,
            "email": "user@example.com",
            "exp": datetime.now(UTC) + exp_delta,
        },
        secret,
        algorithm=config.AUTHENTICATION_ALGORITHM,
    )


class FakeUserDb:
    def __init__(self) -> None:
        self.fetchrow_calls: list[tuple[str, tuple[object, ...]]] = []

    async def fetchrow(self, query: str, *args: object) -> dict[str, object]:
        self.fetchrow_calls.append((query, args))
        assert "WHERE user_id = $1" in query
        assert args == ("user-123",)
        return {
            "email": "user@example.com",
            "user_id": "user-123",
            "first_name": "Ada",
            "last_name": "Lovelace",
            "phone_number": "+15555550123",
            "date_of_birth": datetime(1990, 1, 1, tzinfo=UTC),
            "created_at": datetime(2026, 1, 1, tzinfo=UTC),
            "is_active": True,
            "subscription_type": "free",
        }


def test_expired_access_token_uses_refresh_token_then_loads_user() -> None:
    db = FakeUserDb()
    auth = AuthenticationService(db)  # type: ignore[arg-type]
    expired_access = _jwt(config.AUTHENTICATION_SECRET_KEY, timedelta(seconds=-1))
    valid_refresh = _jwt(config.AUTHENTICATION_REFRESH_SECRET_KEY, timedelta(days=1))

    user = run(auth.getUserFromAccessToken(expired_access, valid_refresh))

    assert user.sub == "user-123"
    assert user.email == "user@example.com"
    assert len(db.fetchrow_calls) == 1


def test_invalid_access_token_does_not_fall_back_to_refresh() -> None:
    db = FakeUserDb()
    auth = AuthenticationService(db)  # type: ignore[arg-type]
    valid_refresh = _jwt(config.AUTHENTICATION_REFRESH_SECRET_KEY, timedelta(days=1))

    with pytest.raises(CredentialException):
        run(auth.getUserFromAccessToken("not-a-jwt", valid_refresh))

    assert db.fetchrow_calls == []


def test_refresh_endpoint_rejects_access_token_signed_with_access_secret() -> None:
    auth = AuthenticationService(object())  # type: ignore[arg-type]
    access_token = _jwt(config.AUTHENTICATION_SECRET_KEY, timedelta(minutes=5))

    with pytest.raises(CredentialException):
        auth.generateAccessTokenFromRefreshToken(access_token)
