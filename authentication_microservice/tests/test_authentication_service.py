import asyncio
from datetime import timedelta

import pytest

from app.errorsHandler.tokenError import CredentialException
from app.models.tokenModel import TokenModel
from app.services.authenticationService import AuthenticationService


class FakeDb:
    def __init__(self, row):
        self.row = row
        self.fetchrow_calls = []

    async def fetchrow(self, query: str, *args):
        self.fetchrow_calls.append((query, args))
        return self.row


def test_refresh_exchange_rejects_access_token(sample_user_row):
    service = AuthenticationService(FakeDb(sample_user_row))
    token_data = TokenModel(sub="user-123", email="person@example.com")
    access_token = service._encodeAccessToken(token_data, timedelta(minutes=5))

    with pytest.raises(CredentialException):
        service.generateAccessTokenFromRefreshToken(access_token)


def test_expired_access_token_uses_refresh_token_then_loads_user(sample_user_row):
    db = FakeDb(sample_user_row)
    service = AuthenticationService(db)
    token_data = TokenModel(sub="user-123", email="person@example.com")
    expired_access_token = service._encodeAccessToken(token_data, timedelta(seconds=-1))
    refresh_token = service._encodeRefreshToken(token_data, timedelta(days=1))

    user = asyncio.run(
        service.getUserFromAccessToken(expired_access_token, refresh_token),
    )

    assert user.sub == "user-123"
    assert user.email == "person@example.com"
    assert db.fetchrow_calls == [
        ("SELECT * FROM users WHERE user_id = $1", ("user-123",)),
    ]


def test_invalid_access_token_does_not_attempt_refresh_or_user_lookup(sample_user_row):
    db = FakeDb(sample_user_row)
    service = AuthenticationService(db)
    token_data = TokenModel(sub="user-123", email="person@example.com")
    wrong_secret_access_token = service._encodeRefreshToken(token_data, timedelta(days=1))
    refresh_token = service._encodeRefreshToken(token_data, timedelta(days=1))

    with pytest.raises(CredentialException):
        asyncio.run(
            service.getUserFromAccessToken(wrong_secret_access_token, refresh_token),
        )

    assert db.fetchrow_calls == []
