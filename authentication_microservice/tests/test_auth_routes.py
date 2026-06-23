from datetime import UTC, datetime

import pytest
from fastapi.testclient import TestClient

from app.api.depends.auth import get_authentication_service
from app.models.tokenModel import Token
from app.models.userModel import UserModel
from main import app


@pytest.fixture
def client():
    yield TestClient(app)
    app.dependency_overrides.clear()


class FakeAuth:
    def __init__(self):
        self.login_requests = []
        self.register_requests = []
        self.refresh_tokens = []
        self.user_token_pairs = []

    async def loginUser(self, request):
        self.login_requests.append(request)
        return (
            Token(accessToken="access-token-value", tokenType="ACCESS_TOKEN"),
            Token(accessToken="refresh-token-value", tokenType="REFRESH_TOKEN"),
        )

    async def registerUser(self, request):
        self.register_requests.append(request)
        return (
            Token(accessToken="new-access-token", tokenType="ACCESS_TOKEN"),
            Token(accessToken="new-refresh-token", tokenType="REFRESH_TOKEN"),
        )

    def generateAccessTokenFromRefreshToken(self, refresh_token):
        self.refresh_tokens.append(refresh_token)
        return Token(
            accessToken=f"access-from-{refresh_token}",
            tokenType="ACCESS_TOKEN",
        )

    async def getUserFromAccessToken(self, access_token, refresh_token):
        self.user_token_pairs.append((access_token, refresh_token))
        return UserModel(
            email="user@example.com",
            sub="user-123",
            userFirstName="test",
            userLastName="user",
            phoneNumber="+15555550123",
            dateOfBirth=datetime(2000, 1, 1, tzinfo=UTC),
            createdAt=datetime(2026, 1, 1, tzinfo=UTC),
            isActive=True,
            subscriptionType="free",
        )


def override_auth(fake_auth):
    app.dependency_overrides[get_authentication_service] = lambda: fake_auth


def set_cookie_headers(response):
    return response.headers.get_list("set-cookie")


@pytest.mark.parametrize(
    ("path", "payload", "access_value", "refresh_value"),
    [
        (
            "/userservices/v1/login",
            {"email": "user@example.com", "password": "StrongPass1!"},
            "access-token-value",
            "refresh-token-value",
        ),
        (
            "/userservices/v1/register",
            {
                "email": "user@example.com",
                "password": "StrongPass1!",
                "dateOfBirth": "2000-01-01T00:00:00Z",
                "firstName": "Test",
                "lastName": "User",
                "phoneNumber": "+15555550123",
            },
            "new-access-token",
            "new-refresh-token",
        ),
    ],
)
def test_login_and_register_issue_secure_http_only_cookies(
    client,
    path,
    payload,
    access_value,
    refresh_value,
):
    fake_auth = FakeAuth()
    override_auth(fake_auth)

    response = client.post(path, json=payload)

    assert response.status_code == 200
    cookies = set_cookie_headers(response)
    assert any(
        f"access_token={access_value}" in cookie
        and "HttpOnly" in cookie
        and "Secure" in cookie
        for cookie in cookies
    )
    assert any(
        f"refresh_token={refresh_value}" in cookie
        and "HttpOnly" in cookie
        and "Secure" in cookie
        for cookie in cookies
    )


def test_refresh_prefers_cookie_token_over_body_token(client):
    fake_auth = FakeAuth()
    override_auth(fake_auth)

    response = client.post(
        "/userservices/v1/refresh",
        cookies={"refresh_token": "cookie-token"},
        json={"refresh_token": "body-token"},
    )

    assert response.status_code == 200
    assert response.json() == {
        "accessToken": "access-from-cookie-token",
        "tokenType": "ACCESS_TOKEN",
    }
    assert fake_auth.refresh_tokens == ["cookie-token"]


def test_refresh_returns_credential_error_when_token_missing(client):
    fake_auth = FakeAuth()
    override_auth(fake_auth)

    response = client.post("/userservices/v1/refresh")

    assert response.status_code == 401
    assert response.json() == {
        "code": "token_error",
        "message": "No Refresh Token provided",
    }
    assert fake_auth.refresh_tokens == []


def test_get_user_from_token_requires_access_and_refresh_cookies(client):
    fake_auth = FakeAuth()
    override_auth(fake_auth)

    response = client.get(
        "/userservices/v1/getUserFromToken",
        cookies={"access_token": "access-cookie", "refresh_token": "refresh-cookie"},
    )

    assert response.status_code == 200
    assert response.json()["sub"] == "user-123"
    assert fake_auth.user_token_pairs == [("access-cookie", "refresh-cookie")]


@pytest.mark.parametrize(
    ("cookies", "message"),
    [
        ({}, "Unauthorized Access: No Access Token provided"),
        (
            {"access_token": "access-cookie"},
            "Unauthorized Access: No Refresh Token provided",
        ),
    ],
)
def test_get_user_from_token_rejects_missing_required_cookies(client, cookies, message):
    fake_auth = FakeAuth()
    override_auth(fake_auth)

    response = client.get("/userservices/v1/getUserFromToken", cookies=cookies)

    assert response.status_code == 401
    assert response.json() == {"code": "login_error", "message": message}
    assert fake_auth.user_token_pairs == []
