import asyncio
from datetime import UTC, datetime, timedelta

import jwt  # type: ignore
import pytest
from fastapi import Response  # type: ignore

import app.services.authenticationService as auth_module
from app.api.version1.getUserFromToken import getUserFromToken
from app.api.version1.login import login
from app.api.version1.refresh import refresh
from app.errorsHandler.loginError import NotAuthorized
from app.errorsHandler.tokenError import CredentialException
from app.models.loginModel import LoginRequest
from app.models.tokenModel import RefreshRequest, Token, TokenModel
from app.models.userModel import UserModel
from app.services.authenticationService import AuthenticationService
from configurations.config import config


def _run(coro):
    return asyncio.run(coro)


def _user(sub: str = "user-123", email: str = "person@example.com") -> UserModel:
    now = datetime(2026, 5, 18, tzinfo=UTC)
    return UserModel(
        email=email,
        sub=sub,
        userFirstName="test",
        userLastName="user",
        phoneNumber="+15555550123",
        dateOfBirth=datetime(1990, 1, 1, tzinfo=UTC),
        createdAt=now,
        isActive=True,
        subscriptionType="free",
    )


def _jwt(secret: str, claims: dict, expires_in: timedelta) -> str:
    payload = dict(claims)
    payload["exp"] = datetime.now(UTC) + expires_in
    return jwt.encode(
        payload,
        secret,
        algorithm=config.AUTHENTICATION_ALGORITHM,
    )


def _patch_user_service(monkeypatch, returned_user: UserModel):
    calls: list[tuple[object, str]] = []

    class FakeUserService:
        def __init__(self, db):
            self.db = db

        async def getUserFromUserId(self, user_id: str) -> UserModel:
            calls.append((self.db, user_id))
            return returned_user

    monkeypatch.setattr(auth_module, "UserService", FakeUserService)
    return calls


def _cookie_headers(response: Response) -> list[str]:
    return [
        value.decode()
        for key, value in response.raw_headers
        if key == b"set-cookie"
    ]


def test_get_user_from_expired_access_token_refreshes_and_loads_user(monkeypatch):
    service = AuthenticationService(db="db-sentinel")
    expected_user = _user()
    calls = _patch_user_service(monkeypatch, expected_user)
    expired_access_token = _jwt(
        config.AUTHENTICATION_SECRET_KEY,
        {"sub": expected_user.sub, "email": expected_user.email},
        expires_in=timedelta(seconds=-1),
    )
    refresh_token = service._encodeRefreshToken(
        TokenModel(sub=expected_user.sub, email=expected_user.email),
        expireDelta=timedelta(days=1),
    )

    user = _run(service.getUserFromAccessToken(expired_access_token, refresh_token))

    assert user == expected_user
    assert calls == [("db-sentinel", expected_user.sub)]


def test_get_user_from_invalid_access_token_does_not_refresh(monkeypatch):
    service = AuthenticationService(db="db-sentinel")
    wrong_secret_access_token = _jwt(
        "not-the-access-secret-but-long-enough",
        {"sub": "user-123", "email": "person@example.com"},
        expires_in=timedelta(minutes=5),
    )
    refresh_token = service._encodeRefreshToken(
        TokenModel(sub="user-123", email="person@example.com"),
        expireDelta=timedelta(days=1),
    )

    def fail_if_refreshed(_refresh_token: str):
        raise AssertionError("invalid access tokens must not use refresh tokens")

    monkeypatch.setattr(
        service,
        "generateAccessTokenFromRefreshToken",
        fail_if_refreshed,
    )

    with pytest.raises(CredentialException):
        _run(service.getUserFromAccessToken(wrong_secret_access_token, refresh_token))


def test_generate_access_token_from_refresh_token_requires_subject_claim():
    service = AuthenticationService(db=None)
    refresh_token_without_subject = _jwt(
        config.AUTHENTICATION_REFRESH_SECRET_KEY,
        {"email": "person@example.com"},
        expires_in=timedelta(days=1),
    )

    with pytest.raises(CredentialException):
        service.generateAccessTokenFromRefreshToken(refresh_token_without_subject)


def test_get_user_from_token_rejects_missing_cookie_credentials():
    class UnusedAuth:
        async def getUserFromAccessToken(self, access_token: str, refresh_token: str):
            raise AssertionError("auth service should not be called")

    with pytest.raises(NotAuthorized, match="No Access Token"):
        _run(
            getUserFromToken(
                access_token=None,
                refresh_token="refresh-token",
                auth=UnusedAuth(),
            )
        )

    with pytest.raises(NotAuthorized, match="No Refresh Token"):
        _run(
            getUserFromToken(
                access_token="access-token",
                refresh_token=None,
                auth=UnusedAuth(),
            )
        )


def test_get_user_from_token_delegates_cookie_tokens_to_auth_service():
    expected_user = _user()

    class FakeAuth:
        async def getUserFromAccessToken(
            self,
            access_token: str,
            refresh_token: str,
        ) -> UserModel:
            assert access_token == "access-token"
            assert refresh_token == "refresh-token"
            return expected_user

    user = _run(
        getUserFromToken(
            access_token="access-token",
            refresh_token="refresh-token",
            auth=FakeAuth(),
        )
    )

    assert user == expected_user


def test_refresh_prefers_cookie_token_over_json_body():
    class FakeAuth:
        def __init__(self):
            self.tokens: list[str] = []

        def generateAccessTokenFromRefreshToken(self, refresh_token: str) -> Token:
            self.tokens.append(refresh_token)
            return Token(accessToken=f"access-for-{refresh_token}", tokenType="ACCESS_TOKEN")

    auth = FakeAuth()

    token = _run(
        refresh(
            auth=auth,
            refresh_token_cookie="cookie-refresh",
            body=RefreshRequest(refresh_token="body-refresh"),
        )
    )

    assert token == Token(accessToken="access-for-cookie-refresh", tokenType="ACCESS_TOKEN")
    assert auth.tokens == ["cookie-refresh"]


def test_login_sets_secure_http_only_token_cookies():
    class FakeAuth:
        async def loginUser(self, request: LoginRequest):
            assert request.email == "person@example.com"
            return (
                Token(accessToken="access-token", tokenType="ACCESS_TOKEN"),
                Token(accessToken="refresh-token", tokenType="REFRESH_TOKEN"),
            )

    response = Response()

    result = _run(
        login(
            request=LoginRequest(email="person@example.com", password="Password1!"),
            response=response,
            auth=FakeAuth(),
        )
    )

    cookies = _cookie_headers(response)
    assert result.status == "success"
    assert any(
        "access_token=access-token" in cookie
        and "HttpOnly" in cookie
        and "Secure" in cookie
        for cookie in cookies
    )
    assert any(
        "refresh_token=refresh-token" in cookie
        and "HttpOnly" in cookie
        and "Secure" in cookie
        for cookie in cookies
    )
