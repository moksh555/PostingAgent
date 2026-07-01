from fastapi.testclient import TestClient  # type: ignore
import pytest

from app.api.depends.auth import get_authentication_service
from app.models.tokenModel import Token
from main import app


@pytest.fixture
def fake_auth(sample_user):
    class FakeAuth:
        def __init__(self):
            self.refresh_tokens: list[str] = []
            self.access_refresh_pairs: list[tuple[str, str]] = []

        def generateAccessTokenFromRefreshToken(self, refresh_token: str) -> Token:
            self.refresh_tokens.append(refresh_token)
            return Token(
                accessToken=f"access-for-{refresh_token}",
                tokenType="ACCESS_TOKEN",
            )

        async def getUserFromAccessToken(self, access_token: str, refresh_token: str):
            self.access_refresh_pairs.append((access_token, refresh_token))
            return sample_user

    return FakeAuth()


@pytest.fixture
def client(fake_auth):
    app.dependency_overrides[get_authentication_service] = lambda: fake_auth
    try:
        yield TestClient(app)
    finally:
        app.dependency_overrides.clear()


def test_refresh_prefers_httponly_cookie_over_body(client, fake_auth):
    response = client.post(
        "/userservices/v1/refresh",
        headers={"Cookie": "refresh_token=cookie-token"},
        json={"refresh_token": "body-token"},
    )

    assert response.status_code == 200
    assert response.json() == {
        "accessToken": "access-for-cookie-token",
        "tokenType": "ACCESS_TOKEN",
    }
    assert fake_auth.refresh_tokens == ["cookie-token"]


def test_refresh_rejects_missing_cookie_and_body(client, fake_auth):
    response = client.post("/userservices/v1/refresh")

    assert response.status_code == 401
    assert response.json() == {
        "code": "token_error",
        "message": "No Refresh Token provided",
    }
    assert fake_auth.refresh_tokens == []


@pytest.mark.parametrize(
    ("cookie_header", "message"),
    [
        (None, "Unauthorized Access: No Access Token provided"),
        ("access_token=access-only", "Unauthorized Access: No Refresh Token provided"),
    ],
)
def test_get_user_from_token_requires_access_and_refresh_cookies(
    client,
    fake_auth,
    cookie_header,
    message,
):
    headers = {"Cookie": cookie_header} if cookie_header else {}

    response = client.get("/userservices/v1/getUserFromToken", headers=headers)

    assert response.status_code == 401
    assert response.json() == {"code": "login_error", "message": message}
    assert fake_auth.access_refresh_pairs == []


def test_get_user_from_token_forwards_cookie_pair_to_auth_service(
    client,
    fake_auth,
    sample_user,
):
    response = client.get(
        "/userservices/v1/getUserFromToken",
        headers={"Cookie": "access_token=access-token; refresh_token=refresh-token"},
    )

    assert response.status_code == 200
    body = response.json()
    assert body["sub"] == sample_user.sub
    assert body["email"] == sample_user.email
    assert body["isActive"] is True
    assert fake_auth.access_refresh_pairs == [("access-token", "refresh-token")]
