import asyncio
from datetime import UTC, datetime, timedelta

import jwt
import pytest
from fastapi import Response

from app.api.version1.getUserFromToken import getUserFromToken
from app.api.version1.login import login
from app.api.version1.refresh import refresh
from app.errorsHandler.loginError import NotAuthorized
from app.errorsHandler.tokenError import CredentialException
from app.models.loginModel import LoginRequest
from app.models.tokenModel import RefreshRequest, Token, TokenModel
from app.models.userModel import UserModel
from app.services import authenticationService as auth_module
from app.services.authenticationService import AuthenticationService
from configurations.config import config


def _run(coro):
    return asyncio.run(coro)


def _sample_user() -> UserModel:
    return UserModel(
        email="person@example.com",
        sub="user-123",
        userFirstName="person",
        userLastName="example",
        phoneNumber="5551234567",
        dateOfBirth=datetime(1990, 1, 1, tzinfo=UTC),
        createdAt=datetime(2026, 1, 1, tzinfo=UTC),
        isActive=True,
        subscriptionType="free",
    )


def _cookie_headers(response: Response) -> list[str]:
    return [
        value.decode("latin-1")
        for name, value in response.raw_headers
        if name.lower() == b"set-cookie"
    ]


def test_refresh_token_exchange_issues_access_token_signed_with_access_secret():
    service = AuthenticationService(db=object())
    refresh_token = service._encodeRefreshToken(
        TokenModel(sub="user-123", email="person@example.com"),
        timedelta(days=1),
    )

    new_access = service.generateAccessTokenFromRefreshToken(refresh_token)

    assert new_access.tokenType == "ACCESS_TOKEN"
    payload = jwt.decode(
        new_access.accessToken,
        config.AUTHENTICATION_SECRET_KEY,
        algorithms=[config.AUTHENTICATION_ALGORITHM],
    )
    assert payload["sub"] == "user-123"
    assert payload["email"] == "person@example.com"


def test_refresh_token_exchange_rejects_access_tokens():
    service = AuthenticationService(db=object())
    access_token = service._encodeAccessToken(
        TokenModel(sub="user-123", email="person@example.com"),
        timedelta(minutes=1),
    )

    with pytest.raises(CredentialException):
        service.generateAccessTokenFromRefreshToken(access_token)


def test_expired_access_token_uses_refresh_token_to_load_user(monkeypatch):
    calls: list[str] = []
    user = _sample_user()

    class FakeUserService:
        def __init__(self, db):
            self.db = db

        async def getUserFromUserId(self, user_id: str) -> UserModel:
            calls.append(user_id)
            return user

    monkeypatch.setattr(auth_module, "UserService", FakeUserService)
    service = AuthenticationService(db=object())
    expired_access = service._encodeAccessToken(
        TokenModel(sub=user.sub, email=user.email),
        timedelta(seconds=-1),
    )
    refresh_token = service._encodeRefreshToken(
        TokenModel(sub=user.sub, email=user.email),
        timedelta(days=1),
    )

    result = _run(service.getUserFromAccessToken(expired_access, refresh_token))

    assert result == user
    assert calls == [user.sub]


def test_refresh_endpoint_prefers_httponly_cookie_over_body_token():
    class FakeAuth:
        def __init__(self):
            self.seen_refresh_token = None

        def generateAccessTokenFromRefreshToken(self, refresh_token: str) -> Token:
            self.seen_refresh_token = refresh_token
            return Token(accessToken="new-access-token", tokenType="ACCESS_TOKEN")

    auth = FakeAuth()

    result = _run(
        refresh(
            auth=auth,
            refresh_token_cookie="cookie-refresh-token",
            body=RefreshRequest(refresh_token="body-refresh-token"),
        )
    )

    assert result == Token(accessToken="new-access-token", tokenType="ACCESS_TOKEN")
    assert auth.seen_refresh_token == "cookie-refresh-token"


def test_refresh_endpoint_requires_refresh_token():
    with pytest.raises(CredentialException, match="No Refresh Token provided"):
        _run(refresh(auth=object(), refresh_token_cookie=None, body=None))


def test_get_user_from_token_requires_cookie_tokens():
    with pytest.raises(NotAuthorized, match="No Access Token provided"):
        _run(getUserFromToken(access_token=None, refresh_token="refresh", auth=object()))

    with pytest.raises(NotAuthorized, match="No Refresh Token provided"):
        _run(getUserFromToken(access_token="access", refresh_token=None, auth=object()))


def test_get_user_from_token_passes_cookie_tokens_to_auth_service():
    class FakeAuth:
        def __init__(self):
            self.seen_tokens = None

        async def getUserFromAccessToken(
            self,
            access_token: str,
            refresh_token: str,
        ) -> UserModel:
            self.seen_tokens = (access_token, refresh_token)
            return _sample_user()

    auth = FakeAuth()

    result = _run(
        getUserFromToken(
            access_token="access-cookie-token",
            refresh_token="refresh-cookie-token",
            auth=auth,
        )
    )

    assert result == _sample_user()
    assert auth.seen_tokens == ("access-cookie-token", "refresh-cookie-token")


def test_login_sets_tokens_as_secure_httponly_cookies():
    class FakeAuth:
        async def loginUser(self, request: LoginRequest) -> tuple[Token, Token]:
            assert request.email == "person@example.com"
            return (
                Token(accessToken="access-token", tokenType="ACCESS_TOKEN"),
                Token(accessToken="refresh-token", tokenType="REFRESH_TOKEN"),
            )

    response = Response()

    result = _run(
        login(
            request=LoginRequest(email="person@example.com", password="CorrectHorse1!"),
            response=response,
            auth=FakeAuth(),
        )
    )

    cookies = _cookie_headers(response)
    assert result.message == "Login successful"
    assert any(
        "access_token=access-token" in cookie
        and "HttpOnly" in cookie
        and "Secure" in cookie
        and "Max-Age=1800" in cookie
        for cookie in cookies
    )
    assert any(
        "refresh_token=refresh-token" in cookie
        and "HttpOnly" in cookie
        and "Secure" in cookie
        and "Max-Age=432000" in cookie
        for cookie in cookies
    )
