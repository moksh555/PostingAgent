from fastapi.testclient import TestClient

from app.api.depends.auth import get_authentication_service
from app.models.tokenModel import Token
from main import app


class FakeAuthService:
    def __init__(self):
        self.refresh_tokens_seen = []

    async def loginUser(self, request):
        return (
            Token(accessToken="access-token-value", tokenType="ACCESS_TOKEN"),
            Token(accessToken="refresh-token-value", tokenType="REFRESH_TOKEN"),
        )

    async def registerUser(self, request):
        return (
            Token(accessToken="registered-access-token", tokenType="ACCESS_TOKEN"),
            Token(accessToken="registered-refresh-token", tokenType="REFRESH_TOKEN"),
        )

    def generateAccessTokenFromRefreshToken(self, refresh_token: str):
        self.refresh_tokens_seen.append(refresh_token)
        return Token(accessToken=f"access-from-{refresh_token}", tokenType="ACCESS_TOKEN")


def _client_with_auth(fake_auth: FakeAuthService) -> TestClient:
    app.dependency_overrides[get_authentication_service] = lambda: fake_auth
    return TestClient(app)


def _set_cookie_headers(response) -> list[str]:
    return response.headers.get_list("set-cookie")


def teardown_function():
    app.dependency_overrides.clear()


def test_login_sets_secure_httponly_access_and_refresh_cookies():
    fake_auth = FakeAuthService()
    client = _client_with_auth(fake_auth)

    response = client.post(
        "/userservices/v1/login",
        json={"email": "user@example.com", "password": "ValidPass123!"},
    )

    assert response.status_code == 200
    assert response.json() == {"message": "Login successful", "status": "success"}
    set_cookie_headers = _set_cookie_headers(response)
    assert any(
        "refresh_token=refresh-token-value" in cookie
        and "HttpOnly" in cookie
        and "Secure" in cookie
        and "Max-Age=432000" in cookie
        for cookie in set_cookie_headers
    )
    assert any(
        "access_token=access-token-value" in cookie
        and "HttpOnly" in cookie
        and "Secure" in cookie
        and "Max-Age=1800" in cookie
        for cookie in set_cookie_headers
    )


def test_register_sets_secure_httponly_access_and_refresh_cookies():
    fake_auth = FakeAuthService()
    client = _client_with_auth(fake_auth)

    response = client.post(
        "/userservices/v1/register",
        json={
            "email": "user@example.com",
            "password": "ValidPass123!",
            "dateOfBirth": "1990-01-01T00:00:00Z",
            "firstName": "Test",
            "lastName": "User",
            "phoneNumber": "1234567890",
        },
    )

    assert response.status_code == 200
    assert response.json() == {"message": "Register successful", "status": "success"}
    set_cookie_headers = _set_cookie_headers(response)
    assert any(
        "refresh_token=registered-refresh-token" in cookie
        and "HttpOnly" in cookie
        and "Secure" in cookie
        and "Max-Age=432000" in cookie
        for cookie in set_cookie_headers
    )
    assert any(
        "access_token=registered-access-token" in cookie
        and "HttpOnly" in cookie
        and "Secure" in cookie
        and "Max-Age=1800" in cookie
        for cookie in set_cookie_headers
    )


def test_refresh_prefers_refresh_cookie_over_body_token():
    fake_auth = FakeAuthService()
    client = _client_with_auth(fake_auth)
    client.cookies.set("refresh_token", "cookie-refresh")

    response = client.post(
        "/userservices/v1/refresh",
        json={"refresh_token": "body-refresh"},
    )

    assert response.status_code == 200
    assert response.json() == {
        "accessToken": "access-from-cookie-refresh",
        "tokenType": "ACCESS_TOKEN",
    }
    assert fake_auth.refresh_tokens_seen == ["cookie-refresh"]


def test_refresh_accepts_body_token_when_cookie_missing():
    fake_auth = FakeAuthService()
    client = _client_with_auth(fake_auth)

    response = client.post(
        "/userservices/v1/refresh",
        json={"refresh_token": "body-refresh"},
    )

    assert response.status_code == 200
    assert response.json() == {
        "accessToken": "access-from-body-refresh",
        "tokenType": "ACCESS_TOKEN",
    }
    assert fake_auth.refresh_tokens_seen == ["body-refresh"]


def test_refresh_requires_cookie_or_body_token():
    fake_auth = FakeAuthService()
    client = _client_with_auth(fake_auth)

    response = client.post("/userservices/v1/refresh")

    assert response.status_code == 401
    assert response.json() == {
        "code": "token_error",
        "message": "No Refresh Token provided",
    }
    assert fake_auth.refresh_tokens_seen == []
