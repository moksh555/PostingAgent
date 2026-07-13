from dataclasses import dataclass, field

import pytest
from fastapi.testclient import TestClient

from app.models.tokenModel import Token


@dataclass
class FakeAuth:
    sample_user: object | None = None
    refresh_inputs: list[str] = field(default_factory=list)
    user_token_inputs: list[tuple[str, str]] = field(default_factory=list)

    def generateAccessTokenFromRefreshToken(self, refresh_token: str) -> Token:
        self.refresh_inputs.append(refresh_token)
        return Token(accessToken=f"new-access-for-{refresh_token}", tokenType="ACCESS_TOKEN")

    async def getUserFromAccessToken(self, access_token: str, refresh_token: str):
        self.user_token_inputs.append((access_token, refresh_token))
        return self.sample_user

    async def loginUser(self, request_obj):
        return (
            Token(accessToken="login-access-token", tokenType="ACCESS_TOKEN"),
            Token(accessToken="login-refresh-token", tokenType="REFRESH_TOKEN"),
        )

    async def registerUser(self, request_obj):
        return (
            Token(accessToken="register-access-token", tokenType="ACCESS_TOKEN"),
            Token(accessToken="register-refresh-token", tokenType="REFRESH_TOKEN"),
        )


@pytest.fixture
def auth_client(sample_user):
    from app.api.depends.auth import get_authentication_service
    from main import app

    fake_auth = FakeAuth(sample_user=sample_user)
    app.dependency_overrides[get_authentication_service] = lambda: fake_auth
    try:
        yield TestClient(app), fake_auth
    finally:
        app.dependency_overrides.clear()


def test_refresh_prefers_cookie_over_body(auth_client):
    client, fake_auth = auth_client

    response = client.post(
        "/userservices/v1/refresh",
        cookies={"refresh_token": "cookie-refresh"},
        json={"refresh_token": "body-refresh"},
    )

    assert response.status_code == 200
    assert response.json() == {
        "accessToken": "new-access-for-cookie-refresh",
        "tokenType": "ACCESS_TOKEN",
    }
    assert fake_auth.refresh_inputs == ["cookie-refresh"]


def test_refresh_falls_back_to_body_when_cookie_missing(auth_client):
    client, fake_auth = auth_client

    response = client.post(
        "/userservices/v1/refresh",
        json={"refresh_token": "body-refresh"},
    )

    assert response.status_code == 200
    assert response.json()["accessToken"] == "new-access-for-body-refresh"
    assert fake_auth.refresh_inputs == ["body-refresh"]


def test_refresh_requires_token(auth_client):
    client, fake_auth = auth_client

    response = client.post("/userservices/v1/refresh", json={})

    assert response.status_code == 401
    assert response.json() == {
        "code": "token_error",
        "message": "No Refresh Token provided",
    }
    assert fake_auth.refresh_inputs == []


def test_get_user_from_token_requires_access_and_refresh_cookies(auth_client):
    client, fake_auth = auth_client

    missing_access = client.get(
        "/userservices/v1/getUserFromToken",
        cookies={"refresh_token": "refresh-token"},
    )
    missing_refresh = client.get(
        "/userservices/v1/getUserFromToken",
        cookies={"access_token": "access-token"},
    )

    assert missing_access.status_code == 401
    assert missing_access.json()["message"] == "Unauthorized Access: No Access Token provided"
    assert missing_refresh.status_code == 401
    assert missing_refresh.json()["message"] == "Unauthorized Access: No Refresh Token provided"
    assert fake_auth.user_token_inputs == []


def test_get_user_from_token_forwards_cookie_pair(auth_client, sample_user):
    client, fake_auth = auth_client

    response = client.get(
        "/userservices/v1/getUserFromToken",
        cookies={
            "access_token": "access-token",
            "refresh_token": "refresh-token",
        },
    )

    assert response.status_code == 200
    assert response.json()["sub"] == sample_user.sub
    assert response.json()["email"] == sample_user.email
    assert fake_auth.user_token_inputs == [("access-token", "refresh-token")]


@pytest.mark.parametrize(
    ("path", "payload", "expected_access", "expected_refresh"),
    [
        (
            "/userservices/v1/login",
            {"email": "user@example.com", "password": "ValidPass1!"},
            "login-access-token",
            "login-refresh-token",
        ),
        (
            "/userservices/v1/register",
            {
                "email": "new.user@example.com",
                "password": "ValidPass1!",
                "dateOfBirth": "1990-01-01T00:00:00Z",
                "firstName": "Ada",
                "lastName": "Lovelace",
                "phoneNumber": "+15551234567",
            },
            "register-access-token",
            "register-refresh-token",
        ),
    ],
)
def test_login_and_register_issue_secure_http_only_auth_cookies(
    auth_client,
    path,
    payload,
    expected_access,
    expected_refresh,
):
    client, _fake_auth = auth_client

    response = client.post(path, json=payload)

    assert response.status_code == 200
    set_cookie_headers = response.headers.get_list("set-cookie")
    access_cookie = next(cookie for cookie in set_cookie_headers if cookie.startswith("access_token="))
    refresh_cookie = next(cookie for cookie in set_cookie_headers if cookie.startswith("refresh_token="))

    assert expected_access in access_cookie
    assert "HttpOnly" in access_cookie
    assert "Secure" in access_cookie
    assert "Max-Age=1800" in access_cookie

    assert expected_refresh in refresh_cookie
    assert "HttpOnly" in refresh_cookie
    assert "Secure" in refresh_cookie
    assert "Max-Age=432000" in refresh_cookie
