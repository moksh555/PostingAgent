import asyncio
from datetime import timedelta
from unittest.mock import Mock

import pytest

from app.errorsHandler.tokenError import CredentialException
from app.models.tokenModel import TokenModel
from app.services import authenticationService as auth_module


def _service() -> auth_module.AuthenticationService:
    return auth_module.AuthenticationService(db=object())


def test_expired_access_token_uses_refresh_token_to_load_user(monkeypatch, sample_user):
    service = _service()
    access_token = service._encodeAccessToken(
        TokenModel(sub=sample_user.sub, email=sample_user.email),
        expireDelta=timedelta(seconds=-1),
    )
    refresh_token = service._encodeRefreshToken(
        TokenModel(sub=sample_user.sub, email=sample_user.email),
        expireDelta=timedelta(days=1),
    )
    user_ids_seen: list[str] = []

    class FakeUserService:
        def __init__(self, db):
            self.db = db

        async def getUserFromUserId(self, user_id: str):
            user_ids_seen.append(user_id)
            return sample_user

    monkeypatch.setattr(auth_module, "UserService", FakeUserService)

    user = asyncio.run(service.getUserFromAccessToken(access_token, refresh_token))

    assert user == sample_user
    assert user_ids_seen == [sample_user.sub]


def test_invalid_access_token_does_not_fall_back_to_refresh(monkeypatch, sample_user):
    service = _service()
    token_data = TokenModel(sub=sample_user.sub, email=sample_user.email)
    access_token = service._encodeRefreshToken(token_data, expireDelta=timedelta(days=1))
    refresh_token = service._encodeRefreshToken(token_data, expireDelta=timedelta(days=1))
    refresh_spy = Mock(side_effect=AssertionError("refresh should not be attempted"))
    monkeypatch.setattr(service, "generateAccessTokenFromRefreshToken", refresh_spy)

    with pytest.raises(CredentialException):
        asyncio.run(service.getUserFromAccessToken(access_token, refresh_token))

    refresh_spy.assert_not_called()


def test_refresh_token_must_be_signed_with_refresh_secret(sample_user):
    service = _service()
    access_token = service._encodeAccessToken(
        TokenModel(sub=sample_user.sub, email=sample_user.email),
        expireDelta=timedelta(minutes=1),
    )

    with pytest.raises(CredentialException):
        service.generateAccessTokenFromRefreshToken(access_token)
