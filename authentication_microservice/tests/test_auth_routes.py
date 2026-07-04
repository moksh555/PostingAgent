from datetime import UTC, datetime

import pytest

from app.api.depends.auth import get_authentication_service
from app.models.tokenModel import Token
from main import app


class FakeRouteAuth:
    def __init__(self, user=None):
        self.user = user
        self.generated_from: list[str] = []
        self.session_calls: list[tuple[str, str]] = []
        self.login_payload = None
        self.register_payload = None

    def generateAccessTokenFromRefreshToken(self, refresh_token: str):
        self.generated_from.append(refresh_token)
        return Token(
            accessToken=f"access-from-{refresh_token}",
            tokenType="ACCESS_TOKEN",
        )

    async def getUserFromAccessToken(self, access_token: str, refresh_token: str):
        self.session_calls.append((access_token, refresh_token))
        return self.user

    async def loginUser(self, request):
        self.login_payload = request
        return (
            Token(accessToken="access-token", tokenType="ACCESS_TOKEN"),
            Token(accessToken="refresh-token", tokenType="REFRESH_TOKEN"),
        )

    async def registerUser(self, request):
        self.register_payload = request
        return (
            Token(accessToken="access-token", tokenType="ACCESS_TOKEN"),
            Token(accessToken="refresh-token", tokenType="REFRESH_TOKEN"),
        )


def override_auth(fake_auth):
    app.dependency_overrides[get_authentication_service] = lambda: fake_auth


def set_cookie_values(response):
    return response.headers.get_list("set-cookie")


def assert_auth_cookies_are_secure(response):
    cookies = set_cookie_values(response)
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


def test_refresh_prefers_http_only_cookie_over_body(client):
    fake_auth = FakeRouteAuth()
    override_auth(fake_auth)

    response = client.post(
        "/userservices/v1/refresh",
        cookies={"refresh_token": "cookie-refresh"},
        json={"refresh_token": "body-refresh"},
    )

    assert response.status_code == 200
    assert response.json() == {
        "accessToken": "access-from-cookie-refresh",
        "tokenType": "ACCESS_TOKEN",
    }
    assert fake_auth.generated_from == ["cookie-refresh"]


def test_refresh_rejects_missing_refresh_token(client):
    fake_auth = FakeRouteAuth()
    override_auth(fake_auth)

    response = client.post("/userservices/v1/refresh")

    assert response.status_code == 401
    assert response.json() == {
        "code": "token_error",
        "message": "No Refresh Token provided",
    }
    assert fake_auth.generated_from == []


@pytest.mark.parametrize(
    ("cookies", "message"),
    [
        ({}, "Unauthorized Access: No Access Token provided"),
        ({"access_token": "access"}, "Unauthorized Access: No Refresh Token provided"),
    ],
)
def test_get_user_from_token_requires_cookie_pair(client, cookies, message):
    fake_auth = FakeRouteAuth()
    override_auth(fake_auth)

    response = client.get("/userservices/v1/getUserFromToken", cookies=cookies)

    assert response.status_code == 401
    assert response.json() == {"code": "login_error", "message": message}
    assert fake_auth.session_calls == []


def test_get_user_from_token_forwards_cookie_pair_to_auth_service(client, sample_user):
    fake_auth = FakeRouteAuth(user=sample_user)
    override_auth(fake_auth)

    response = client.get(
        "/userservices/v1/getUserFromToken",
        cookies={
            "access_token": "access-token",
            "refresh_token": "refresh-token",
        },
    )

    assert response.status_code == 200
    body = response.json()
    assert body["email"] == sample_user.email
    assert body["sub"] == sample_user.sub
    assert fake_auth.session_calls == [("access-token", "refresh-token")]


def test_login_sets_secure_http_only_auth_cookies(client):
    fake_auth = FakeRouteAuth()
    override_auth(fake_auth)

    response = client.post(
        "/userservices/v1/login",
        json={"email": "USER@Example.com", "password": "StrongPass1!"},
    )

    assert response.status_code == 200
    assert response.json() == {"message": "Login successful", "status": "success"}
    assert fake_auth.login_payload.email == "USER@Example.com"
    assert_auth_cookies_are_secure(response)


def test_register_sets_secure_http_only_auth_cookies(client):
    fake_auth = FakeRouteAuth()
    override_auth(fake_auth)

    response = client.post(
        "/userservices/v1/register",
        json={
            "email": "user@example.com",
            "password": "StrongPass1!",
            "dateOfBirth": datetime(1990, 1, 1, tzinfo=UTC).isoformat(),
            "firstName": "Test",
            "lastName": "User",
            "phoneNumber": "+15551234567",
        },
    )

    assert response.status_code == 200
    assert response.json() == {"message": "Register successful", "status": "success"}
    assert fake_auth.register_payload.email == "user@example.com"
    assert_auth_cookies_are_secure(response)
