from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
from fastapi.testclient import TestClient

from app.api.depends.auth import get_authentication_service
from app.api.router import router as main_router
from app.errorsHandler.baseError import AuthenticationError
from app.models.tokenModel import Token


class FakeAuthService:
    def __init__(self, user_model=None):
        self.user_model = user_model
        self.refresh_inputs: list[str] = []
        self.access_refresh_pairs: list[tuple[str, str]] = []

    async def loginUser(self, payload):
        return (
            Token(accessToken="access-from-login", tokenType="ACCESS_TOKEN"),
            Token(accessToken="refresh-from-login", tokenType="REFRESH_TOKEN"),
        )

    async def registerUser(self, payload):
        return (
            Token(accessToken="access-from-register", tokenType="ACCESS_TOKEN"),
            Token(accessToken="refresh-from-register", tokenType="REFRESH_TOKEN"),
        )

    def generateAccessTokenFromRefreshToken(self, refresh_token: str):
        self.refresh_inputs.append(refresh_token)
        return Token(accessToken=f"access-for-{refresh_token}", tokenType="ACCESS_TOKEN")

    async def getUserFromAccessToken(self, access_token: str, refresh_token: str):
        self.access_refresh_pairs.append((access_token, refresh_token))
        return self.user_model


def _client_for(fake_auth: FakeAuthService) -> TestClient:
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
    return TestClient(app)


def test_login_sets_secure_httponly_access_and_refresh_cookies():
    client = _client_for(FakeAuthService())

    response = client.post(
        "/userservices/v1/login",
        json={"email": "user@example.com", "password": "StrongPass1!"},
    )

    assert response.status_code == 200
    set_cookie_headers = response.headers.get_list("set-cookie")
    assert any(
        "refresh_token=refresh-from-login" in header
        and "HttpOnly" in header
        and "Secure" in header
        for header in set_cookie_headers
    )
    assert any(
        "access_token=access-from-login" in header
        and "HttpOnly" in header
        and "Secure" in header
        for header in set_cookie_headers
    )


def test_register_sets_secure_httponly_access_and_refresh_cookies():
    client = _client_for(FakeAuthService())

    response = client.post(
        "/userservices/v1/register",
        json={
            "email": "user@example.com",
            "password": "StrongPass1!",
            "dateOfBirth": "2000-01-01T00:00:00Z",
            "firstName": "Ada",
            "lastName": "Lovelace",
            "phoneNumber": "+15551234567",
        },
    )

    assert response.status_code == 200
    set_cookie_headers = response.headers.get_list("set-cookie")
    assert any(
        "refresh_token=refresh-from-register" in header
        and "HttpOnly" in header
        and "Secure" in header
        for header in set_cookie_headers
    )
    assert any(
        "access_token=access-from-register" in header
        and "HttpOnly" in header
        and "Secure" in header
        for header in set_cookie_headers
    )


def test_refresh_prefers_cookie_token_over_body_token():
    fake_auth = FakeAuthService()
    client = _client_for(fake_auth)
    client.cookies.set("refresh_token", "cookie-token")

    response = client.post(
        "/userservices/v1/refresh",
        json={"refresh_token": "body-token"},
    )

    assert response.status_code == 200
    assert response.json() == {
        "accessToken": "access-for-cookie-token",
        "tokenType": "ACCESS_TOKEN",
    }
    assert fake_auth.refresh_inputs == ["cookie-token"]


def test_refresh_uses_body_token_when_cookie_missing():
    fake_auth = FakeAuthService()
    client = _client_for(fake_auth)

    response = client.post(
        "/userservices/v1/refresh",
        json={"refresh_token": "body-token"},
    )

    assert response.status_code == 200
    assert response.json()["accessToken"] == "access-for-body-token"
    assert fake_auth.refresh_inputs == ["body-token"]


def test_refresh_rejects_missing_refresh_token():
    client = _client_for(FakeAuthService())

    response = client.post("/userservices/v1/refresh", json={})

    assert response.status_code == 401
    assert response.json() == {
        "code": "token_error",
        "message": "No Refresh Token provided",
    }


def test_get_user_from_token_requires_both_cookies(user_model):
    missing_access_client = _client_for(FakeAuthService(user_model=user_model))
    missing_access_client.cookies.set("refresh_token", "refresh-token")
    missing_refresh_client = _client_for(FakeAuthService(user_model=user_model))
    missing_refresh_client.cookies.set("access_token", "access-token")

    missing_access = missing_access_client.get(
        "/userservices/v1/getUserFromToken",
    )
    missing_refresh = missing_refresh_client.get(
        "/userservices/v1/getUserFromToken",
    )

    assert missing_access.status_code == 401
    assert missing_access.json()["message"] == "Unauthorized Access: No Access Token provided"
    assert missing_refresh.status_code == 401
    assert missing_refresh.json()["message"] == "Unauthorized Access: No Refresh Token provided"


def test_get_user_from_token_forwards_cookie_pair_to_auth_service(user_model):
    fake_auth = FakeAuthService(user_model=user_model)
    client = _client_for(fake_auth)
    client.cookies.set("access_token", "access-token")
    client.cookies.set("refresh_token", "refresh-token")

    response = client.get("/userservices/v1/getUserFromToken")

    assert response.status_code == 200
    assert response.json()["sub"] == user_model.sub
    assert fake_auth.access_refresh_pairs == [("access-token", "refresh-token")]
