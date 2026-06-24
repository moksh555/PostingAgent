from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
from fastapi.testclient import TestClient

from app.api.depends.auth import get_authentication_service
from app.api.version1.getUserFromToken import router as get_user_from_token_router
from app.api.version1.refresh import router as refresh_router
from app.errorsHandler.baseError import AuthenticationError
from app.models.tokenModel import Token


class StubAuthenticationService:
    def __init__(self, user):
        self.user = user
        self.refresh_tokens = []
        self.access_token_pairs = []

    def generateAccessTokenFromRefreshToken(self, refreshToken: str) -> Token:
        self.refresh_tokens.append(refreshToken)
        return Token(
            accessToken=f"access-for-{refreshToken}",
            tokenType="ACCESS_TOKEN",
        )

    async def getUserFromAccessToken(self, accessToken: str, refreshToken: str):
        self.access_token_pairs.append((accessToken, refreshToken))
        return self.user


async def auth_error_handler(_request: Request, exc: AuthenticationError):
    return JSONResponse(
        status_code=exc.status_code,
        content={"code": exc.code, "message": exc.message},
    )


def build_client(auth_service: StubAuthenticationService) -> TestClient:
    app = FastAPI()
    app.include_router(refresh_router)
    app.include_router(get_user_from_token_router)
    app.add_exception_handler(AuthenticationError, auth_error_handler)
    app.dependency_overrides[get_authentication_service] = lambda: auth_service
    return TestClient(app)


def test_refresh_prefers_cookie_token_over_body_token(sample_user):
    auth = StubAuthenticationService(sample_user)
    client = build_client(auth)

    response = client.post(
        "/refresh",
        cookies={"refresh_token": "cookie-refresh"},
        json={"refresh_token": "body-refresh"},
    )

    assert response.status_code == 200
    assert response.json() == {
        "accessToken": "access-for-cookie-refresh",
        "tokenType": "ACCESS_TOKEN",
    }
    assert auth.refresh_tokens == ["cookie-refresh"]


def test_refresh_uses_body_token_when_cookie_missing(sample_user):
    auth = StubAuthenticationService(sample_user)
    client = build_client(auth)

    response = client.post("/refresh", json={"refresh_token": "body-refresh"})

    assert response.status_code == 200
    assert response.json()["accessToken"] == "access-for-body-refresh"
    assert auth.refresh_tokens == ["body-refresh"]


def test_refresh_rejects_missing_token(sample_user):
    auth = StubAuthenticationService(sample_user)
    client = build_client(auth)

    response = client.post("/refresh", json={})

    assert response.status_code == 401
    assert response.json() == {
        "code": "token_error",
        "message": "No Refresh Token provided",
    }
    assert auth.refresh_tokens == []


def test_get_user_from_token_requires_access_cookie(sample_user):
    auth = StubAuthenticationService(sample_user)
    client = build_client(auth)

    response = client.get(
        "/getUserFromToken",
        cookies={"refresh_token": "refresh-token"},
    )

    assert response.status_code == 401
    assert response.json() == {
        "code": "login_error",
        "message": "Unauthorized Access: No Access Token provided",
    }
    assert auth.access_token_pairs == []


def test_get_user_from_token_passes_cookie_pair_to_auth_service(sample_user):
    auth = StubAuthenticationService(sample_user)
    client = build_client(auth)

    response = client.get(
        "/getUserFromToken",
        cookies={
            "access_token": "access-token",
            "refresh_token": "refresh-token",
        },
    )

    assert response.status_code == 200
    assert response.json()["sub"] == "user-123"
    assert response.json()["email"] == "person@example.com"
    assert auth.access_token_pairs == [("access-token", "refresh-token")]
