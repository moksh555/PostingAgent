from fastapi.testclient import TestClient
import pytest

from app.api.depends.auth import get_authentication_service
from app.models.tokenModel import Token
from main import app


class FakeAuthenticationService:
    def __init__(self) -> None:
        self.login_requests = []
        self.refresh_tokens = []

    async def loginUser(self, request):
        self.login_requests.append(request)
        return (
            Token(accessToken="access-cookie-value", tokenType="ACCESS_TOKEN"),
            Token(accessToken="refresh-cookie-value", tokenType="REFRESH_TOKEN"),
        )

    def generateAccessTokenFromRefreshToken(self, refresh_token: str) -> Token:
        self.refresh_tokens.append(refresh_token)
        return Token(accessToken=f"access-for-{refresh_token}", tokenType="ACCESS_TOKEN")


@pytest.fixture
def client_and_auth():
    fake_auth = FakeAuthenticationService()
    app.dependency_overrides[get_authentication_service] = lambda: fake_auth
    client = TestClient(app)
    try:
        yield client, fake_auth
    finally:
        app.dependency_overrides.clear()
        client.close()


def test_login_sets_http_only_access_and_refresh_cookies(client_and_auth):
    client, fake_auth = client_and_auth

    response = client.post(
        "/userservices/v1/login",
        json={"email": "User@example.com", "password": "ValidPass1!"},
    )

    assert response.status_code == 200
    assert response.json() == {"message": "Login successful", "status": "success"}
    assert fake_auth.login_requests[0].email == "User@example.com"

    set_cookie_headers = response.headers.get_list("set-cookie")
    refresh_cookie = next(
        header for header in set_cookie_headers if header.startswith("refresh_token=")
    )
    access_cookie = next(
        header for header in set_cookie_headers if header.startswith("access_token=")
    )
    assert "refresh_token=refresh-cookie-value" in refresh_cookie
    assert "Max-Age=432000" in refresh_cookie
    assert "HttpOnly" in refresh_cookie
    assert "Secure" in refresh_cookie
    assert "access_token=access-cookie-value" in access_cookie
    assert "Max-Age=1800" in access_cookie
    assert "HttpOnly" in access_cookie
    assert "Secure" in access_cookie


def test_refresh_prefers_refresh_cookie_over_json_body(client_and_auth):
    client, fake_auth = client_and_auth
    client.cookies.set("refresh_token", "cookie-refresh-token")

    response = client.post(
        "/userservices/v1/refresh",
        json={"refresh_token": "body-refresh-token"},
    )

    assert response.status_code == 200
    assert response.json() == {
        "accessToken": "access-for-cookie-refresh-token",
        "tokenType": "ACCESS_TOKEN",
    }
    assert fake_auth.refresh_tokens == ["cookie-refresh-token"]


def test_refresh_uses_json_body_when_cookie_is_absent(client_and_auth):
    client, fake_auth = client_and_auth

    response = client.post(
        "/userservices/v1/refresh",
        json={"refresh_token": "body-refresh-token"},
    )

    assert response.status_code == 200
    assert response.json() == {
        "accessToken": "access-for-body-refresh-token",
        "tokenType": "ACCESS_TOKEN",
    }
    assert fake_auth.refresh_tokens == ["body-refresh-token"]


def test_refresh_without_cookie_or_body_returns_token_error(client_and_auth):
    client, fake_auth = client_and_auth

    response = client.post("/userservices/v1/refresh")

    assert response.status_code == 401
    assert response.json() == {
        "code": "token_error",
        "message": "No Refresh Token provided",
    }
    assert fake_auth.refresh_tokens == []


def test_get_user_from_token_requires_access_cookie(client_and_auth):
    client, _fake_auth = client_and_auth
    client.cookies.set("refresh_token", "refresh-cookie")

    response = client.get("/userservices/v1/getUserFromToken")

    assert response.status_code == 401
    assert response.json() == {
        "code": "login_error",
        "message": "Unauthorized Access: No Access Token provided",
    }
