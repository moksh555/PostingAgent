from datetime import UTC, datetime

import pytest

from app.models.tokenModel import Token


class FakeAuthService:
    def __init__(self, user=None) -> None:
        self.user = user
        self.login_requests = []
        self.register_requests = []
        self.refresh_requests = []
        self.user_token_requests = []

    async def loginUser(self, request):
        self.login_requests.append(request)
        return (
            Token(accessToken="access-token", tokenType="ACCESS_TOKEN"),
            Token(accessToken="refresh-token", tokenType="REFRESH_TOKEN"),
        )

    async def registerUser(self, request):
        self.register_requests.append(request)
        return (
            Token(accessToken="access-token", tokenType="ACCESS_TOKEN"),
            Token(accessToken="refresh-token", tokenType="REFRESH_TOKEN"),
        )

    def generateAccessTokenFromRefreshToken(self, refresh_token: str):
        self.refresh_requests.append(refresh_token)
        return Token(accessToken=f"access-for-{refresh_token}", tokenType="ACCESS_TOKEN")

    async def getUserFromAccessToken(self, access_token: str, refresh_token: str):
        self.user_token_requests.append((access_token, refresh_token))
        return self.user


def _cookie_headers(response):
    return response.headers.get_list("set-cookie")


def _assert_auth_cookies(response):
    headers = _cookie_headers(response)
    assert any(
        header.startswith("refresh_token=refresh-token;")
        and "HttpOnly" in header
        and "Secure" in header
        and "Max-Age=432000" in header
        for header in headers
    )
    assert any(
        header.startswith("access_token=access-token;")
        and "HttpOnly" in header
        and "Secure" in header
        and "Max-Age=1800" in header
        for header in headers
    )


def test_login_sets_secure_http_only_tokens_without_returning_them(client_factory):
    auth = FakeAuthService()
    client = client_factory(auth)

    response = client.post(
        "/userservices/v1/login",
        json={"email": "User@Example.COM", "password": "ValidPass1!"},
    )

    assert response.status_code == 200
    assert response.json() == {"message": "Login successful", "status": "success"}
    _assert_auth_cookies(response)
    assert auth.login_requests[0].email == "User@Example.COM"


def test_register_sets_secure_http_only_tokens_without_returning_them(client_factory):
    auth = FakeAuthService()
    client = client_factory(auth)

    response = client.post(
        "/userservices/v1/register",
        json={
            "email": "user@example.com",
            "password": "ValidPass1!",
            "dateOfBirth": datetime(1990, 1, 1, tzinfo=UTC).isoformat(),
            "firstName": "Test",
            "lastName": "User",
            "phoneNumber": "+15551234567",
        },
    )

    assert response.status_code == 200
    assert response.json() == {"message": "Register successful", "status": "success"}
    _assert_auth_cookies(response)
    assert auth.register_requests[0].email == "user@example.com"


def test_refresh_prefers_cookie_over_body_token(client_factory):
    auth = FakeAuthService()
    client = client_factory(auth)

    response = client.post(
        "/userservices/v1/refresh",
        cookies={"refresh_token": "cookie-refresh"},
        json={"refresh_token": "body-refresh"},
    )

    assert response.status_code == 200
    assert response.json() == {
        "accessToken": "access-for-cookie-refresh",
        "tokenType": "ACCESS_TOKEN",
    }
    assert auth.refresh_requests == ["cookie-refresh"]


def test_refresh_uses_body_token_when_cookie_missing(client_factory):
    auth = FakeAuthService()
    client = client_factory(auth)

    response = client.post(
        "/userservices/v1/refresh",
        json={"refresh_token": "body-refresh"},
    )

    assert response.status_code == 200
    assert response.json()["accessToken"] == "access-for-body-refresh"
    assert auth.refresh_requests == ["body-refresh"]


def test_refresh_requires_cookie_or_body_token(client_factory):
    auth = FakeAuthService()
    client = client_factory(auth)

    response = client.post("/userservices/v1/refresh")

    assert response.status_code == 401
    assert response.json() == {
        "code": "token_error",
        "message": "No Refresh Token provided",
    }
    assert auth.refresh_requests == []


@pytest.mark.parametrize(
    ("cookies", "message"),
    [
        (
            {"refresh_token": "refresh-cookie"},
            "Unauthorized Access: No Access Token provided",
        ),
        (
            {"access_token": "access-cookie"},
            "Unauthorized Access: No Refresh Token provided",
        ),
    ],
)
def test_get_user_from_token_requires_both_cookies(client_factory, cookies, message):
    auth = FakeAuthService()
    client = client_factory(auth)

    response = client.get("/userservices/v1/getUserFromToken", cookies=cookies)

    assert response.status_code == 401
    assert response.json() == {"code": "login_error", "message": message}
    assert auth.user_token_requests == []


def test_get_user_from_token_forwards_cookie_pair_to_auth_service(
    client_factory,
    sample_user,
):
    auth = FakeAuthService(sample_user)
    client = client_factory(auth)

    response = client.get(
        "/userservices/v1/getUserFromToken",
        cookies={
            "access_token": "access-cookie",
            "refresh_token": "refresh-cookie",
        },
    )

    assert response.status_code == 200
    assert response.json()["sub"] == sample_user.sub
    assert auth.user_token_requests == [("access-cookie", "refresh-cookie")]
