"""Regression tests for JWT separation and session restoration."""

import asyncio
from datetime import UTC, datetime, timedelta

import jwt
import pytest

from app.errorsHandler.loginError import NotAuthorized
from app.errorsHandler.tokenError import CredentialException
from app.models.tokenModel import TokenModel
from app.models.userModel import UserModel
from app.services.authenticationService import AuthenticationService
from app.services.userService import UserService
from configurations.config import config


def _user() -> UserModel:
    return UserModel(
        sub="user-123",
        email="person@example.com",
        userFirstName="person",
        userLastName="example",
        phoneNumber="+1 555 123 4567",
        dateOfBirth=datetime(1990, 1, 1, tzinfo=UTC),
        createdAt=datetime(2026, 1, 1, tzinfo=UTC),
        isActive=True,
        subscriptionType="free",
    )


def _expired_token(secret: str, *, include_sub: bool = True) -> str:
    payload = {
        "email": "person@example.com",
        "exp": datetime.now(UTC) - timedelta(minutes=1),
    }
    if include_sub:
        payload["sub"] = "user-123"
    return jwt.encode(payload, secret, algorithm=config.AUTHENTICATION_ALGORITHM)


def _service() -> AuthenticationService:
    return AuthenticationService(db=object())  # type: ignore[arg-type]


def test_access_and_refresh_tokens_use_separate_signing_keys():
    service = _service()
    claims = TokenModel(sub="user-123", email="person@example.com")

    access = service._encodeAccessToken(claims)
    refresh = service._encodeRefreshToken(claims)

    assert jwt.decode(
        access,
        config.AUTHENTICATION_SECRET_KEY,
        algorithms=[config.AUTHENTICATION_ALGORITHM],
    )["sub"] == "user-123"
    assert jwt.decode(
        refresh,
        config.AUTHENTICATION_REFRESH_SECRET_KEY,
        algorithms=[config.AUTHENTICATION_ALGORITHM],
    )["sub"] == "user-123"
    with pytest.raises(jwt.InvalidSignatureError):
        jwt.decode(
            refresh,
            config.AUTHENTICATION_SECRET_KEY,
            algorithms=[config.AUTHENTICATION_ALGORITHM],
        )


def test_valid_refresh_token_issues_access_token():
    service = _service()
    refresh = service._encodeRefreshToken(
        TokenModel(sub="user-123", email="person@example.com"),
    )

    result = service.generateAccessTokenFromRefreshToken(refresh)
    payload = jwt.decode(
        result.accessToken,
        config.AUTHENTICATION_SECRET_KEY,
        algorithms=[config.AUTHENTICATION_ALGORITHM],
    )

    assert result.tokenType == "ACCESS_TOKEN"
    assert payload["sub"] == "user-123"
    assert payload["email"] == "person@example.com"


def test_access_token_cannot_be_exchanged_as_refresh_token():
    service = _service()
    access = service._encodeAccessToken(
        TokenModel(sub="user-123", email="person@example.com"),
    )

    with pytest.raises(CredentialException):
        service.generateAccessTokenFromRefreshToken(access)


def test_expired_refresh_token_is_rejected():
    with pytest.raises(NotAuthorized, match="Refresh token expired"):
        _service().generateAccessTokenFromRefreshToken(
            _expired_token(config.AUTHENTICATION_REFRESH_SECRET_KEY),
        )


def test_refresh_token_without_subject_is_rejected():
    token = jwt.encode(
        {
            "email": "person@example.com",
            "exp": datetime.now(UTC) + timedelta(days=1),
        },
        config.AUTHENTICATION_REFRESH_SECRET_KEY,
        algorithm=config.AUTHENTICATION_ALGORITHM,
    )

    with pytest.raises(CredentialException):
        _service().generateAccessTokenFromRefreshToken(token)


def test_valid_access_token_loads_user_without_refresh(monkeypatch):
    service = _service()
    expected = _user()
    access = service._encodeAccessToken(
        TokenModel(sub=expected.sub, email=expected.email),
    )
    loaded_ids: list[str] = []

    async def fake_get_user(_self, user_id: str):
        loaded_ids.append(user_id)
        return expected

    def unexpected_refresh(_token: str):
        raise AssertionError("valid access tokens must not trigger refresh")

    monkeypatch.setattr(UserService, "getUserFromUserId", fake_get_user)
    monkeypatch.setattr(service, "generateAccessTokenFromRefreshToken", unexpected_refresh)

    result = asyncio.run(service.getUserFromAccessToken(access, "unused"))

    assert result == expected
    assert loaded_ids == ["user-123"]


def test_expired_access_token_refreshes_and_retries_lookup(monkeypatch):
    service = _service()
    expected = _user()
    refresh = service._encodeRefreshToken(
        TokenModel(sub=expected.sub, email=expected.email),
    )
    loaded_ids: list[str] = []

    async def fake_get_user(_self, user_id: str):
        loaded_ids.append(user_id)
        return expected

    monkeypatch.setattr(UserService, "getUserFromUserId", fake_get_user)

    result = asyncio.run(
        service.getUserFromAccessToken(
            _expired_token(config.AUTHENTICATION_SECRET_KEY),
            refresh,
        ),
    )

    assert result == expected
    assert loaded_ids == ["user-123"]


def test_invalid_access_token_does_not_trigger_refresh(monkeypatch):
    service = _service()
    refresh_calls: list[str] = []
    invalid_access = jwt.encode(
        {
            "sub": "user-123",
            "email": "person@example.com",
            "exp": datetime.now(UTC) + timedelta(minutes=5),
        },
        "a-different-signing-key-at-least-32-bytes",
        algorithm=config.AUTHENTICATION_ALGORITHM,
    )

    def track_refresh(token: str):
        refresh_calls.append(token)
        raise AssertionError("invalid access tokens must not trigger refresh")

    monkeypatch.setattr(service, "generateAccessTokenFromRefreshToken", track_refresh)

    with pytest.raises(CredentialException):
        asyncio.run(service.getUserFromAccessToken(invalid_access, "valid-looking"))
    assert refresh_calls == []


def test_expired_bearer_access_token_does_not_use_refresh():
    with pytest.raises(CredentialException, match="Access token expired"):
        asyncio.run(
            _service().decodeAccessToken(
                _expired_token(config.AUTHENTICATION_SECRET_KEY),
            ),
        )
