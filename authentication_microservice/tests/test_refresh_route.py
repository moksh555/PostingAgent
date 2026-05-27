from app.api.depends.auth import get_authentication_service
from app.models.tokenModel import Token
from main import app


class RecordingRefreshAuth:
    def __init__(self) -> None:
        self.refresh_tokens: list[str] = []

    def generateAccessTokenFromRefreshToken(self, refresh_token: str) -> Token:
        self.refresh_tokens.append(refresh_token)
        return Token(
            accessToken=f"access-for-{refresh_token}",
            tokenType="ACCESS_TOKEN",
        )


def test_refresh_uses_body_token_when_cookie_missing(client):
    auth = RecordingRefreshAuth()
    app.dependency_overrides[get_authentication_service] = lambda: auth

    response = client.post(
        "/userservices/v1/refresh",
        json={"refresh_token": "body-refresh-token"},
    )

    assert response.status_code == 200
    assert response.json() == {
        "accessToken": "access-for-body-refresh-token",
        "tokenType": "ACCESS_TOKEN",
    }
    assert auth.refresh_tokens == ["body-refresh-token"]


def test_refresh_prefers_http_only_cookie_over_body_token(client):
    auth = RecordingRefreshAuth()
    app.dependency_overrides[get_authentication_service] = lambda: auth

    response = client.post(
        "/userservices/v1/refresh",
        cookies={"refresh_token": "cookie-refresh-token"},
        json={"refresh_token": "body-refresh-token"},
    )

    assert response.status_code == 200
    assert response.json()["accessToken"] == "access-for-cookie-refresh-token"
    assert auth.refresh_tokens == ["cookie-refresh-token"]


def test_refresh_rejects_requests_without_refresh_token(client):
    auth = RecordingRefreshAuth()
    app.dependency_overrides[get_authentication_service] = lambda: auth

    response = client.post("/userservices/v1/refresh")

    assert response.status_code == 401
    assert response.json() == {
        "code": "token_error",
        "message": "No Refresh Token provided",
    }
    assert auth.refresh_tokens == []
