from dataclasses import dataclass, field

import pytest
from fastapi.testclient import TestClient

from app.api.depends.auth import get_authentication_service
from app.models.tokenModel import Token
from main import app


@dataclass
class FakeAuthenticationService:
    refresh_inputs: list[str] = field(default_factory=list)
    token_inputs: list[tuple[str, str]] = field(default_factory=list)

    async def loginUser(self, _request):
        return (
            Token(accessToken="access-from-login", tokenType="ACCESS_TOKEN"),
            Token(accessToken="refresh-from-login", tokenType="REFRESH_TOKEN"),
        )

    async def registerUser(self, _request):
        return (
            Token(accessToken="access-from-register", tokenType="ACCESS_TOKEN"),
            Token(accessToken="refresh-from-register", tokenType="REFRESH_TOKEN"),
        )

    def generateAccessTokenFromRefreshToken(self, refresh_token: str):
        self.refresh_inputs.append(refresh_token)
        return Token(accessToken=f"access-for-{refresh_token}", tokenType="ACCESS_TOKEN")

    async def getUserFromAccessToken(self, access_token: str, refresh_token: str):
        self.token_inputs.append((access_token, refresh_token))
        return {
            "email": "user@example.com",
            "sub": "user-123",
            "userFirstName": "Test",
            "userLastName": "User",
            "phoneNumber": "1234567890",
            "dateOfBirth": "1990-01-01T00:00:00Z",
            "createdAt": "2026-01-01T12:00:00Z",
            "isActive": True,
            "subscriptionType": "free",
        }


@pytest.fixture
def fake_auth():
    fake = FakeAuthenticationService()
    app.dependency_overrides[get_authentication_service] = lambda: fake
    try:
        yield fake
    finally:
        app.dependency_overrides.clear()


@pytest.fixture
def client(fake_auth):
    test_client = TestClient(app)
    try:
        yield test_client
    finally:
        test_client.close()


@pytest.mark.parametrize(
    ("path", "payload", "access_token", "refresh_token", "message"),
    [
        (
            "/userservices/v1/login",
            {"email": "User@Example.com", "password": "Password123!"},
            "access-from-login",
            "refresh-from-login",
            "Login successful",
        ),
        (
            "/userservices/v1/register",
            {
                "email": "user@example.com",
                "password": "Password123!",
                "dateOfBirth": "1990-01-01T00:00:00Z",
                "firstName": "Test",
                "lastName": "User",
                "phoneNumber": "1234567890",
            },
            "access-from-register",
            "refresh-from-register",
            "Register successful",
        ),
    ],
)
def test_login_and_register_issue_secure_http_only_token_cookies(
    client,
    path,
    payload,
    access_token,
    refresh_token,
    message,
):
    response = client.post(path, json=payload)

    assert response.status_code == 200
    assert response.json() == {"message": message, "status": "success"}
    set_cookie_headers = response.headers.get_list("set-cookie")
    assert any(
        f"access_token={access_token}" in header
        and "HttpOnly" in header
        and "Secure" in header
        for header in set_cookie_headers
    )
    assert any(
        f"refresh_token={refresh_token}" in header
        and "HttpOnly" in header
        and "Secure" in header
        for header in set_cookie_headers
    )


def test_refresh_prefers_http_only_cookie_over_json_body(client, fake_auth):
    client.cookies.set("refresh_token", "cookie-refresh")

    response = client.post(
        "/userservices/v1/refresh",
        json={"refresh_token": "body-refresh"},
    )

    assert response.status_code == 200
    assert response.json() == {
        "accessToken": "access-for-cookie-refresh",
        "tokenType": "ACCESS_TOKEN",
    }
    assert fake_auth.refresh_inputs == ["cookie-refresh"]


def test_refresh_without_cookie_or_body_returns_token_error(client):
    response = client.post("/userservices/v1/refresh")

    assert response.status_code == 401
    assert response.json() == {
        "code": "token_error",
        "message": "No Refresh Token provided",
    }


def test_get_user_from_token_requires_both_cookies(client):
    client.cookies.set("access_token", "access-only")

    response = client.get("/userservices/v1/getUserFromToken")

    assert response.status_code == 401
    assert response.json() == {
        "code": "login_error",
        "message": "Unauthorized Access: No Refresh Token provided",
    }


def test_get_user_from_token_passes_cookie_tokens_to_auth_service(client, fake_auth):
    client.cookies.set("access_token", "access-cookie")
    client.cookies.set("refresh_token", "refresh-cookie")

    response = client.get("/userservices/v1/getUserFromToken")

    assert response.status_code == 200
    assert response.json()["sub"] == "user-123"
    assert fake_auth.token_inputs == [("access-cookie", "refresh-cookie")]
