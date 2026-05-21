from __future__ import annotations

import asyncio
from datetime import UTC, datetime, timedelta
from unittest.mock import Mock

import jwt
import pytest
from fastapi.testclient import TestClient

from app.api.depends.auth import get_authentication_service
from app.errorsHandler.loginError import NotAuthorized
from app.errorsHandler.registerError import RegisterPayloadError
from app.errorsHandler.tokenError import CredentialException
from app.errorsHandler.userError import NoEmailError
from app.models.registerModel import RegisterRequest
from app.models.tokenModel import Token, TokenModel
from app.models.userModel import UserModel
from app.services import authenticationService as auth_module
from app.services.authenticationService import AuthenticationService
from app.services.userService import UserService
from configurations.config import config
from main import app


@pytest.fixture(autouse=True)
def clear_dependency_overrides():
    app.dependency_overrides.clear()
    yield
    app.dependency_overrides.clear()


@pytest.fixture
def auth_service() -> AuthenticationService:
    return AuthenticationService(db=object())


def _token_model() -> TokenModel:
    return TokenModel(sub="user-123", email="user@example.com")


def _jwt_with_refresh_secret(payload: dict, expires_in: timedelta) -> str:
    claims = {**payload, "exp": datetime.now(UTC) + expires_in}
    return jwt.encode(
        claims,
        config.AUTHENTICATION_REFRESH_SECRET_KEY,
        algorithm=config.AUTHENTICATION_ALGORITHM,
    )


def _jwt_with_access_secret(payload: dict, expires_in: timedelta) -> str:
    claims = {**payload, "exp": datetime.now(UTC) + expires_in}
    return jwt.encode(
        claims,
        config.AUTHENTICATION_SECRET_KEY,
        algorithm=config.AUTHENTICATION_ALGORITHM,
    )


def _years_ago(years: int) -> datetime:
    today = datetime.now(UTC)
    try:
        return today.replace(year=today.year - years)
    except ValueError:
        return today.replace(month=2, day=28, year=today.year - years)


def _register_request(**overrides) -> RegisterRequest:
    values = {
        "email": "user@example.com",
        "password": "ValidPass1!",
        "dateOfBirth": _years_ago(30),
        "firstName": "Ada",
        "lastName": "Lovelace",
        "phoneNumber": "+15551234567",
    }
    values.update(overrides)
    return RegisterRequest(**values)


def _user_model(sub: str = "user-123") -> UserModel:
    return UserModel(
        email="user@example.com",
        sub=sub,
        userFirstName="Ada",
        userLastName="Lovelace",
        phoneNumber="+15551234567",
        dateOfBirth=_years_ago(30),
        createdAt=datetime.now(UTC),
        isActive=True,
        subscriptionType="free",
    )


def test_refresh_token_mints_access_token_with_user_claims(
    auth_service: AuthenticationService,
):
    refresh_token = auth_service._encodeRefreshToken(
        _token_model(),
        timedelta(minutes=5),
    )

    token = auth_service.generateAccessTokenFromRefreshToken(refresh_token)

    decoded = jwt.decode(
        token.accessToken,
        config.AUTHENTICATION_SECRET_KEY,
        algorithms=[config.AUTHENTICATION_ALGORITHM],
    )
    assert token.tokenType == "ACCESS_TOKEN"
    assert decoded["sub"] == "user-123"
    assert decoded["email"] == "user@example.com"


@pytest.mark.parametrize(
    ("refresh_token", "expected_error"),
    [
        (
            _jwt_with_refresh_secret(
                {"sub": "user-123", "email": "user@example.com"},
                timedelta(seconds=-1),
            ),
            NotAuthorized,
        ),
        (
            _jwt_with_access_secret(
                {"sub": "user-123", "email": "user@example.com"},
                timedelta(minutes=5),
            ),
            CredentialException,
        ),
        (
            _jwt_with_refresh_secret({"email": "user@example.com"}, timedelta(minutes=5)),
            CredentialException,
        ),
    ],
)
def test_refresh_token_rejects_expired_wrong_secret_and_missing_subject(
    auth_service: AuthenticationService,
    refresh_token: str,
    expected_error: type[Exception],
):
    with pytest.raises(expected_error):
        auth_service.generateAccessTokenFromRefreshToken(refresh_token)


def test_get_user_from_access_token_refreshes_only_when_access_expired(
    auth_service: AuthenticationService,
    monkeypatch: pytest.MonkeyPatch,
):
    expected_user = _user_model()

    class FakeUserService:
        def __init__(self, db):
            self.db = db

        async def getUserFromUserId(self, user_id: str) -> UserModel:
            assert user_id == expected_user.sub
            return expected_user

    monkeypatch.setattr(auth_module, "UserService", FakeUserService)

    expired_access = auth_service._encodeAccessToken(
        _token_model(),
        timedelta(seconds=-1),
    )
    valid_refresh = auth_service._encodeRefreshToken(
        _token_model(),
        timedelta(minutes=5),
    )

    refreshed_user = asyncio.run(
        auth_service.getUserFromAccessToken(expired_access, valid_refresh),
    )

    assert refreshed_user == expected_user

    wrong_secret_access = _jwt_with_refresh_secret(
        {"sub": "user-123", "email": "user@example.com"},
        timedelta(minutes=5),
    )
    refresh_spy = Mock(wraps=auth_service.generateAccessTokenFromRefreshToken)
    monkeypatch.setattr(auth_service, "generateAccessTokenFromRefreshToken", refresh_spy)

    with pytest.raises(CredentialException):
        asyncio.run(
            auth_service.getUserFromAccessToken(wrong_secret_access, valid_refresh),
        )
    refresh_spy.assert_not_called()


def test_login_unknown_email_uses_generic_authorization_error(
    auth_service: AuthenticationService,
    monkeypatch: pytest.MonkeyPatch,
):
    class MissingUserService:
        def __init__(self, db):
            self.db = db

        async def getUserFromEmail(self, email: str, private: bool = False):
            raise NoEmailError("User not found")

    monkeypatch.setattr(auth_module, "UserService", MissingUserService)

    with pytest.raises(NotAuthorized) as exc_info:
        asyncio.run(
            auth_service.authenticateUser("unknown@example.com", "ValidPass1!"),
        )

    assert exc_info.value.message == "Invalid email or password"


def test_refresh_route_accepts_cookie_or_body_refresh_token():
    class FakeAuth:
        def __init__(self):
            self.seen_refresh_tokens: list[str] = []

        def generateAccessTokenFromRefreshToken(self, refresh_token: str) -> Token:
            self.seen_refresh_tokens.append(refresh_token)
            return Token(
                accessToken=f"access-for-{refresh_token}",
                tokenType="ACCESS_TOKEN",
            )

    fake_auth = FakeAuth()
    app.dependency_overrides[get_authentication_service] = lambda: fake_auth
    client = TestClient(app)

    cookie_response = client.post(
        "/userservices/v1/refresh",
        cookies={"refresh_token": "cookie-refresh"},
    )
    body_response = client.post(
        "/userservices/v1/refresh",
        json={"refresh_token": "body-refresh"},
    )

    assert cookie_response.status_code == 200
    assert cookie_response.json() == {
        "accessToken": "access-for-cookie-refresh",
        "tokenType": "ACCESS_TOKEN",
    }
    assert body_response.status_code == 200
    assert body_response.json() == {
        "accessToken": "access-for-body-refresh",
        "tokenType": "ACCESS_TOKEN",
    }
    assert fake_auth.seen_refresh_tokens == ["cookie-refresh", "body-refresh"]


def test_refresh_route_rejects_missing_refresh_token():
    app.dependency_overrides[get_authentication_service] = lambda: AuthenticationService(
        db=object(),
    )

    response = TestClient(app).post("/userservices/v1/refresh")

    assert response.status_code == 401
    assert response.json() == {
        "code": "token_error",
        "message": "No Refresh Token provided",
    }


@pytest.mark.parametrize(
    ("cookies", "message"),
    [
        ({}, "Unauthorized Access: No Access Token provided"),
        ({"access_token": "access-token"}, "Unauthorized Access: No Refresh Token provided"),
    ],
)
def test_get_user_from_token_requires_access_and_refresh_cookies(
    cookies: dict[str, str],
    message: str,
):
    app.dependency_overrides[get_authentication_service] = lambda: AuthenticationService(
        db=object(),
    )
    client = TestClient(app)
    client.cookies.update(cookies)

    response = client.get("/userservices/v1/getUserFromToken")

    assert response.status_code == 401
    assert response.json() == {"code": "login_error", "message": message}


@pytest.mark.parametrize(
    ("payload_overrides", "message"),
    [
        ({"password": "Short1!"}, "Password must be at least 10 characters"),
        (
            {"password": "ValidPassword1"},
            "Password must contain at least one special character",
        ),
        (
            {"dateOfBirth": _years_ago(10)},
            "You must be at least 13 years old to register",
        ),
        ({"phoneNumber": "1234567"}, "Invalid phone number length"),
    ],
)
def test_register_payload_validation_rejects_risky_invalid_inputs(
    payload_overrides: dict,
    message: str,
):
    with pytest.raises(RegisterPayloadError) as exc_info:
        UserService(db=object()).validateUserRegisterPayload(
            _register_request(**payload_overrides),
        )

    assert message in exc_info.value.message
