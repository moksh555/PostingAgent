from datetime import UTC, datetime

import pytest
from fastapi.testclient import TestClient  # type: ignore

from app.api.depends.auth import get_authentication_service
from app.models.tokenModel import Token
from app.models.userModel import UserModel
from main import app


@pytest.fixture(autouse=True)
def clear_dependency_overrides():
    app.dependency_overrides.clear()
    yield
    app.dependency_overrides.clear()


@pytest.fixture
def client():
    return TestClient(app)


def _user() -> UserModel:
    return UserModel(
        email="user@example.com",
        sub="user-123",
        userFirstName="ada",
        userLastName="lovelace",
        phoneNumber="15551234567",
        dateOfBirth=datetime(1990, 1, 1, tzinfo=UTC),
        createdAt=datetime(2026, 1, 1, tzinfo=UTC),
        isActive=True,
        subscriptionType="free",
    )


def _login_payload() -> dict[str, str]:
    return {"email": "user@example.com", "password": "StrongPass1!"}


def _register_payload() -> dict[str, str]:
    return {
        "email": "user@example.com",
        "password": "StrongPass1!",
        "dateOfBirth": "1990-01-01T00:00:00+00:00",
        "firstName": "Ada",
        "lastName": "Lovelace",
        "phoneNumber": "+1 555 123 4567",
    }


def _assert_auth_cookies(response):
    set_cookie = ",".join(response.headers.get_list("set-cookie"))

    assert "refresh_token=refresh-token" in set_cookie
    assert "access_token=access-token" in set_cookie
    assert "HttpOnly" in set_cookie
    assert "Secure" in set_cookie


def _set_client_cookies(client, **cookies: str) -> None:
    client.cookies.clear()
    for name, value in cookies.items():
        client.cookies.set(name, value)


def test_login_sets_secure_http_only_access_and_refresh_cookies(client):
    class FakeAuth:
        async def loginUser(self, request_obj):
            return (
                Token(accessToken="access-token", tokenType="ACCESS_TOKEN"),
                Token(accessToken="refresh-token", tokenType="REFRESH_TOKEN"),
            )

    app.dependency_overrides[get_authentication_service] = lambda: FakeAuth()

    response = client.post("/userservices/v1/login", json=_login_payload())

    assert response.status_code == 200
    assert response.json() == {"message": "Login successful", "status": "success"}
    _assert_auth_cookies(response)


def test_register_sets_secure_http_only_access_and_refresh_cookies(client):
    class FakeAuth:
        async def registerUser(self, request_obj):
            return (
                Token(accessToken="access-token", tokenType="ACCESS_TOKEN"),
                Token(accessToken="refresh-token", tokenType="REFRESH_TOKEN"),
            )

    app.dependency_overrides[get_authentication_service] = lambda: FakeAuth()

    response = client.post("/userservices/v1/register", json=_register_payload())

    assert response.status_code == 200
    assert response.json() == {"message": "Register successful", "status": "success"}
    _assert_auth_cookies(response)


def test_refresh_prefers_cookie_over_body_token(client):
    class FakeAuth:
        seen_tokens: list[str] = []

        def generateAccessTokenFromRefreshToken(self, refresh_token: str) -> Token:
            self.seen_tokens.append(refresh_token)
            return Token(accessToken="new-access", tokenType="ACCESS_TOKEN")

    fake_auth = FakeAuth()
    app.dependency_overrides[get_authentication_service] = lambda: fake_auth
    _set_client_cookies(client, refresh_token="cookie-refresh")

    response = client.post(
        "/userservices/v1/refresh",
        json={"refresh_token": "body-refresh"},
    )

    assert response.status_code == 200
    assert response.json() == {
        "accessToken": "new-access",
        "tokenType": "ACCESS_TOKEN",
    }
    assert fake_auth.seen_tokens == ["cookie-refresh"]


def test_refresh_falls_back_to_body_token(client):
    class FakeAuth:
        seen_tokens: list[str] = []

        def generateAccessTokenFromRefreshToken(self, refresh_token: str) -> Token:
            self.seen_tokens.append(refresh_token)
            return Token(accessToken="new-access", tokenType="ACCESS_TOKEN")

    fake_auth = FakeAuth()
    app.dependency_overrides[get_authentication_service] = lambda: fake_auth

    response = client.post(
        "/userservices/v1/refresh",
        json={"refresh_token": "body-refresh"},
    )

    assert response.status_code == 200
    assert fake_auth.seen_tokens == ["body-refresh"]


def test_refresh_requires_cookie_or_body_token(client):
    class UnusedAuth:
        def generateAccessTokenFromRefreshToken(self, refresh_token: str) -> Token:
            raise AssertionError("refresh should not be called without a token")

    app.dependency_overrides[get_authentication_service] = lambda: UnusedAuth()

    response = client.post("/userservices/v1/refresh", json={})

    assert response.status_code == 401
    assert response.json() == {
        "code": "token_error",
        "message": "No Refresh Token provided",
    }


def test_get_user_from_token_requires_access_and_refresh_cookies(client):
    class UnusedAuth:
        async def getUserFromAccessToken(
            self,
            access_token: str,
            refresh_token: str,
        ) -> UserModel:
            raise AssertionError("auth lookup should not run without both cookies")

    app.dependency_overrides[get_authentication_service] = lambda: UnusedAuth()
    _set_client_cookies(client, refresh_token="refresh-cookie")

    missing_access = client.get(
        "/userservices/v1/getUserFromToken",
    )
    _set_client_cookies(client, access_token="access-cookie")
    missing_refresh = client.get(
        "/userservices/v1/getUserFromToken",
    )

    assert missing_access.status_code == 401
    assert missing_access.json() == {
        "code": "login_error",
        "message": "Unauthorized Access: No Access Token provided",
    }
    assert missing_refresh.status_code == 401
    assert missing_refresh.json() == {
        "code": "login_error",
        "message": "Unauthorized Access: No Refresh Token provided",
    }


def test_get_user_from_token_forwards_cookie_pair_to_auth_service(client):
    class FakeAuth:
        seen_pairs: list[tuple[str, str]] = []

        async def getUserFromAccessToken(
            self,
            access_token: str,
            refresh_token: str,
        ) -> UserModel:
            self.seen_pairs.append((access_token, refresh_token))
            return _user()

    fake_auth = FakeAuth()
    app.dependency_overrides[get_authentication_service] = lambda: fake_auth
    _set_client_cookies(
        client,
        access_token="access-cookie",
        refresh_token="refresh-cookie",
    )

    response = client.get(
        "/userservices/v1/getUserFromToken",
    )

    assert response.status_code == 200
    assert response.json()["sub"] == "user-123"
    assert response.json()["email"] == "user@example.com"
    assert fake_auth.seen_pairs == [("access-cookie", "refresh-cookie")]
