import asyncio
from datetime import timedelta

import jwt
import pytest

from app.errorsHandler.tokenError import CredentialException
from app.models.tokenModel import TokenModel
from app.services.authenticationService import AuthenticationService
from configurations.config import config


class FakeUserDb:
    def __init__(self, row):
        self.row = row
        self.fetchrow_calls = []

    async def fetchrow(self, query, *args):
        self.fetchrow_calls.append((query, args))
        return self.row


def test_refresh_token_mints_access_token_and_rejects_access_token(user_row):
    service = AuthenticationService(FakeUserDb(user_row))
    token_data = TokenModel(sub="user-123", email="user@example.com")

    refresh_token = service._encodeRefreshToken(token_data, timedelta(days=1))
    access_token = service._encodeAccessToken(token_data, timedelta(minutes=5))

    minted = service.generateAccessTokenFromRefreshToken(refresh_token)

    assert minted.tokenType == "ACCESS_TOKEN"
    decoded = jwt.decode(
        minted.accessToken,
        config.AUTHENTICATION_SECRET_KEY,
        algorithms=[config.AUTHENTICATION_ALGORITHM],
    )
    assert decoded["sub"] == "user-123"

    with pytest.raises(CredentialException):
        service.generateAccessTokenFromRefreshToken(access_token)


def test_expired_access_token_refreshes_once_and_loads_user(user_row):
    db = FakeUserDb(user_row)
    service = AuthenticationService(db)
    token_data = TokenModel(sub="user-123", email="user@example.com")
    expired_access_token = service._encodeAccessToken(
        token_data,
        timedelta(seconds=-1),
    )
    refresh_token = service._encodeRefreshToken(token_data, timedelta(days=1))

    user = asyncio.run(
        service.getUserFromAccessToken(expired_access_token, refresh_token),
    )

    assert user.sub == "user-123"
    assert db.fetchrow_calls == [
        ("SELECT * FROM users WHERE user_id = $1", ("user-123",)),
    ]


def test_malformed_access_token_does_not_attempt_refresh_or_user_lookup(user_row):
    db = FakeUserDb(user_row)
    service = AuthenticationService(db)
    token_data = TokenModel(sub="user-123", email="user@example.com")
    refresh_token = service._encodeRefreshToken(token_data, timedelta(days=1))

    with pytest.raises(CredentialException):
        asyncio.run(service.getUserFromAccessToken("not-a-jwt", refresh_token))

    assert db.fetchrow_calls == []
