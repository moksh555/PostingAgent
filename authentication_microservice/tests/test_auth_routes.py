from datetime import datetime

import pytest
from fastapi.testclient import TestClient

from app.api.depends.auth import get_authentication_service
from app.models.tokenModel import Token
from main import app


@pytest.fixture
def client():
    app.dependency_overrides.clear()
    test_client = TestClient(app)
    yield test_client
    test_client.close()
    app.dependency_overrides.clear()


def _cookie_header(response, cookie_name: str) -> str:
    for header in response.headers.get_list("set-cookie"):
        if header.startswith(f"{cookie_name}="):
            return header.lower()
    raise AssertionError(f"Missing {cookie_name} cookie")


@pytest.mark.parametrize(
    ("path", "payload", "auth_method", "message"),
    [
        (
            "/userservices/v1/login",
            {"email": "user@example.com", "password": "correct-password"},
            "loginUser",
            "Login successful",
        ),
        (
            "/userservices/v1/register",
            {
                "email": "user@example.com",
                "password": "correct-password",
                "dateOfBirth": datetime(1990, 1, 1).isoformat(),
                "firstName": "Test",
                "lastName": "User",
                "phoneNumber": "+15555550123",
            },
            "registerUser",
            "Register successful",
        ),
    ],
)
def test_login_and_register_set_secure_http_only_cookies(
    client,
    path,
    payload,
    auth_method,
    message,
):
    methods_called: list[str] = []

    class FakeAuth:
        async def loginUser(self, request_obj):
            methods_called.append("loginUser")
            return (
                Token(accessToken="access-token-value", tokenType="ACCESS_TOKEN"),
                Token(accessToken="refresh-token-value", tokenType="REFRESH_TOKEN"),
            )

        async def registerUser(self, request_obj):
            methods_called.append("registerUser")
            return (
                Token(accessToken="access-token-value", tokenType="ACCESS_TOKEN"),
                Token(accessToken="refresh-token-value", tokenType="REFRESH_TOKEN"),
            )

    app.dependency_overrides[get_authentication_service] = lambda: FakeAuth()

    response = client.post(path, json=payload)

    assert response.status_code == 200
    assert response.json() == {"message": message, "status": "success"}
    assert methods_called == [auth_method]

    access_cookie = _cookie_header(response, "access_token")
    refresh_cookie = _cookie_header(response, "refresh_token")

    assert "access_token=access-token-value" in access_cookie
    assert "httponly" in access_cookie
    assert "secure" in access_cookie
    assert "max-age=1800" in access_cookie

    assert "refresh_token=refresh-token-value" in refresh_cookie
    assert "httponly" in refresh_cookie
    assert "secure" in refresh_cookie
    assert "max-age=432000" in refresh_cookie


@pytest.mark.parametrize(
    ("cookies", "json_body", "expected_refresh"),
    [
        (
            {"refresh_token": "cookie-refresh"},
            {"refresh_token": "body-refresh"},
            "cookie-refresh",
        ),
        ({}, {"refresh_token": "body-refresh"}, "body-refresh"),
    ],
)
def test_refresh_uses_cookie_before_body_fallback(
    client,
    cookies,
    json_body,
    expected_refresh,
):
    refresh_tokens_seen: list[str] = []

    class FakeAuth:
        def generateAccessTokenFromRefreshToken(self, refresh_token: str):
            refresh_tokens_seen.append(refresh_token)
            return Token(accessToken="new-access-token", tokenType="ACCESS_TOKEN")

    app.dependency_overrides[get_authentication_service] = lambda: FakeAuth()

    response = client.post(
        "/userservices/v1/refresh",
        cookies=cookies,
        json=json_body,
    )

    assert response.status_code == 200
    assert response.json() == {
        "accessToken": "new-access-token",
        "tokenType": "ACCESS_TOKEN",
    }
    assert refresh_tokens_seen == [expected_refresh]


def test_refresh_without_cookie_or_body_token_returns_token_error(client):
    class FakeAuth:
        def generateAccessTokenFromRefreshToken(self, refresh_token: str):
            raise AssertionError("missing refresh token should fail before auth service")

    app.dependency_overrides[get_authentication_service] = lambda: FakeAuth()

    response = client.post("/userservices/v1/refresh", json={})

    assert response.status_code == 401
    assert response.json() == {
        "code": "token_error",
        "message": "No Refresh Token provided",
    }


def test_get_user_from_token_requires_both_auth_cookies(client):
    response = client.get(
        "/userservices/v1/getUserFromToken",
        cookies={"access_token": "access-token-only"},
    )

    assert response.status_code == 401
    assert response.json() == {
        "code": "login_error",
        "message": "Unauthorized Access: No Refresh Token provided",
    }
