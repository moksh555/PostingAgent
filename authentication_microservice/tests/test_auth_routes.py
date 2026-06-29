from datetime import UTC, datetime

from fastapi.testclient import TestClient

from app.api.depends.auth import get_authentication_service
from app.models.tokenModel import Token
from app.models.userModel import UserModel


class CookieIssuingAuth:
    def __init__(self) -> None:
        self.requests = []

    async def loginUser(self, request):  # noqa: N802
        self.requests.append(request)
        return (
            Token(accessToken="access-token-value", tokenType="ACCESS_TOKEN"),
            Token(accessToken="refresh-token-value", tokenType="REFRESH_TOKEN"),
        )

    async def registerUser(self, request):  # noqa: N802
        self.requests.append(request)
        return (
            Token(accessToken="access-token-value", tokenType="ACCESS_TOKEN"),
            Token(accessToken="refresh-token-value", tokenType="REFRESH_TOKEN"),
        )


def assert_secure_cookie(set_cookie_headers: list[str], name: str, max_age: int) -> None:
    cookie = next(header for header in set_cookie_headers if header.startswith(f"{name}="))
    assert f"Max-Age={max_age}" in cookie
    assert "HttpOnly" in cookie
    assert "Secure" in cookie


def test_login_sets_access_and_refresh_cookies(auth_app) -> None:
    fake_auth = CookieIssuingAuth()
    auth_app.dependency_overrides[get_authentication_service] = lambda: fake_auth
    client = TestClient(auth_app)

    response = client.post(
        "/userservices/v1/login",
        json={"email": "Person@Example.com", "password": "ValidPass1!"},
    )

    assert response.status_code == 200
    assert response.json() == {"message": "Login successful", "status": "success"}
    set_cookie_headers = response.headers.get_list("set-cookie")
    assert_secure_cookie(set_cookie_headers, "refresh_token", 3600 * 24 * 5)
    assert_secure_cookie(set_cookie_headers, "access_token", 1800)


def test_register_sets_access_and_refresh_cookies(auth_app) -> None:
    fake_auth = CookieIssuingAuth()
    auth_app.dependency_overrides[get_authentication_service] = lambda: fake_auth
    client = TestClient(auth_app)

    response = client.post(
        "/userservices/v1/register",
        json={
            "email": "Person@Example.com",
            "password": "ValidPass1!",
            "dateOfBirth": "2000-01-01T00:00:00Z",
            "firstName": "Person",
            "lastName": "Example",
            "phoneNumber": "+15551234567",
        },
    )

    assert response.status_code == 200
    assert response.json() == {"message": "Register successful", "status": "success"}
    set_cookie_headers = response.headers.get_list("set-cookie")
    assert_secure_cookie(set_cookie_headers, "refresh_token", 3600 * 24 * 5)
    assert_secure_cookie(set_cookie_headers, "access_token", 1800)


class RefreshAuth:
    def __init__(self) -> None:
        self.seen_refresh_tokens: list[str] = []

    def generateAccessTokenFromRefreshToken(self, refresh_token: str):  # noqa: N802
        self.seen_refresh_tokens.append(refresh_token)
        return Token(
            accessToken=f"access-for-{refresh_token}",
            tokenType="ACCESS_TOKEN",
        )


def test_refresh_prefers_cookie_token_over_body_token(auth_app) -> None:
    fake_auth = RefreshAuth()
    auth_app.dependency_overrides[get_authentication_service] = lambda: fake_auth
    client = TestClient(auth_app)

    response = client.post(
        "/userservices/v1/refresh",
        cookies={"refresh_token": "cookie-token"},
        json={"refresh_token": "body-token"},
    )

    assert response.status_code == 200
    assert response.json() == {
        "accessToken": "access-for-cookie-token",
        "tokenType": "ACCESS_TOKEN",
    }
    assert fake_auth.seen_refresh_tokens == ["cookie-token"]


def test_refresh_requires_cookie_or_body_token(auth_app) -> None:
    auth_app.dependency_overrides[get_authentication_service] = lambda: RefreshAuth()
    client = TestClient(auth_app)

    response = client.post("/userservices/v1/refresh")

    assert response.status_code == 401
    assert response.json() == {
        "code": "token_error",
        "message": "No Refresh Token provided",
    }


class GetUserAuth:
    def __init__(self) -> None:
        self.seen_tokens: list[tuple[str, str]] = []

    async def getUserFromAccessToken(self, access_token: str, refresh_token: str):  # noqa: N802
        self.seen_tokens.append((access_token, refresh_token))
        return UserModel(
            email="person@example.com",
            sub="user-1",
            userFirstName="person",
            userLastName="example",
            phoneNumber="+15551234567",
            dateOfBirth=datetime(2000, 1, 1, tzinfo=UTC),
            createdAt=datetime(2026, 1, 1, tzinfo=UTC),
            isActive=True,
            subscriptionType="free",
        )


def test_get_user_from_token_requires_and_forwards_cookie_pair(auth_app) -> None:
    fake_auth = GetUserAuth()
    auth_app.dependency_overrides[get_authentication_service] = lambda: fake_auth
    client = TestClient(auth_app)

    missing_response = client.get(
        "/userservices/v1/getUserFromToken",
        cookies={"access_token": "access-token"},
    )
    assert missing_response.status_code == 401
    assert missing_response.json()["message"] == (
        "Unauthorized Access: No Refresh Token provided"
    )

    response = client.get(
        "/userservices/v1/getUserFromToken",
        cookies={
            "access_token": "access-token",
            "refresh_token": "refresh-token",
        },
    )

    assert response.status_code == 200
    assert response.json()["sub"] == "user-1"
    assert fake_auth.seen_tokens == [("access-token", "refresh-token")]
