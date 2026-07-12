from __future__ import annotations

from datetime import datetime, timezone

import pytest
from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
from fastapi.testclient import TestClient

from app.api.depends.auth import get_authentication_service
from app.api.router import router as main_router
from app.errorsHandler.baseError import AuthenticationError
from app.models.tokenModel import Token


class FakeAuthenticationService:
    def __init__(self, sample_user):
        self.sample_user = sample_user
        self.refresh_token_calls: list[str] = []
        self.get_user_calls: list[tuple[str, str]] = []
        self.login_payloads = []
        self.register_payloads = []

    def generateAccessTokenFromRefreshToken(self, refresh_token: str) -> Token:
        self.refresh_token_calls.append(refresh_token)
        return Token(
            accessToken=f"access-for-{refresh_token}",
            tokenType="ACCESS_TOKEN",
        )

    async def getUserFromAccessToken(self, access_token: str, refresh_token: str):
        self.get_user_calls.append((access_token, refresh_token))
        return self.sample_user

    async def loginUser(self, user_payload):
        self.login_payloads.append(user_payload)
        return (
            Token(accessToken="login-access-token", tokenType="ACCESS_TOKEN"),
            Token(accessToken="login-refresh-token", tokenType="REFRESH_TOKEN"),
        )

    async def registerUser(self, user_payload):
        self.register_payloads.append(user_payload)
        return (
            Token(accessToken="register-access-token", tokenType="ACCESS_TOKEN"),
            Token(accessToken="register-refresh-token", tokenType="REFRESH_TOKEN"),
        )


@pytest.fixture
def fake_auth(sample_user):
    return FakeAuthenticationService(sample_user)


@pytest.fixture
def client(fake_auth):
    app = FastAPI()

    @app.exception_handler(AuthenticationError)
    async def authentication_error_handler(
        _request: Request,
        exc: AuthenticationError,
    ) -> JSONResponse:
        return JSONResponse(
            status_code=exc.status_code,
            content={"code": exc.code, "message": exc.message},
        )

    app.include_router(main_router)
    app.dependency_overrides[get_authentication_service] = lambda: fake_auth

    test_client = TestClient(app, base_url="https://testserver")
    try:
        yield test_client
    finally:
        test_client.close()
        app.dependency_overrides.clear()


def test_refresh_prefers_cookie_over_body(client, fake_auth):
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
    assert fake_auth.refresh_token_calls == ["cookie-refresh-token"]


def test_refresh_uses_body_when_cookie_absent(client, fake_auth):
    response = client.post(
        "/userservices/v1/refresh",
        json={"refresh_token": "body-refresh-token"},
    )

    assert response.status_code == 200
    assert response.json()["accessToken"] == "access-for-body-refresh-token"
    assert fake_auth.refresh_token_calls == ["body-refresh-token"]


def test_refresh_requires_token(client):
    response = client.post("/userservices/v1/refresh", json={})

    assert response.status_code == 401
    assert response.json() == {
        "code": "token_error",
        "message": "No Refresh Token provided",
    }


def test_get_user_from_token_requires_both_cookies(client):
    client.cookies.set("access_token", "access-token-only")

    response = client.get("/userservices/v1/getUserFromToken")

    assert response.status_code == 401
    assert response.json() == {
        "code": "login_error",
        "message": "Unauthorized Access: No Refresh Token provided",
    }


def test_get_user_from_token_forwards_cookie_pair(client, fake_auth, sample_user):
    client.cookies.set("access_token", "access-cookie-token")
    client.cookies.set("refresh_token", "refresh-cookie-token")

    response = client.get("/userservices/v1/getUserFromToken")

    assert response.status_code == 200
    assert response.json()["sub"] == sample_user.sub
    assert response.json()["email"] == sample_user.email
    assert fake_auth.get_user_calls == [
        ("access-cookie-token", "refresh-cookie-token")
    ]


@pytest.mark.parametrize(
    ("path", "payload", "access_token", "refresh_token"),
    [
        (
            "/userservices/v1/login",
            {"email": "person@example.com", "password": "correct-password"},
            "login-access-token",
            "login-refresh-token",
        ),
        (
            "/userservices/v1/register",
            {
                "email": "person@example.com",
                "password": "correct-password",
                "dateOfBirth": datetime(1990, 1, 1, tzinfo=timezone.utc).isoformat(),
                "firstName": "Person",
                "lastName": "Example",
                "phoneNumber": "+15555550123",
            },
            "register-access-token",
            "register-refresh-token",
        ),
    ],
)
def test_login_and_register_issue_secure_httponly_auth_cookies(
    client,
    path,
    payload,
    access_token,
    refresh_token,
):
    response = client.post(path, json=payload)

    assert response.status_code == 200
    set_cookie_headers = response.headers.get_list("set-cookie")
    access_cookie = next(
        header for header in set_cookie_headers if header.startswith("access_token=")
    )
    refresh_cookie = next(
        header for header in set_cookie_headers if header.startswith("refresh_token=")
    )

    assert f"access_token={access_token}" in access_cookie
    assert "HttpOnly" in access_cookie
    assert "Secure" in access_cookie
    assert "Max-Age=1800" in access_cookie

    assert f"refresh_token={refresh_token}" in refresh_cookie
    assert "HttpOnly" in refresh_cookie
    assert "Secure" in refresh_cookie
    assert "Max-Age=432000" in refresh_cookie
