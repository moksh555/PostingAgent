import pytest
from fastapi.testclient import TestClient  # type: ignore

from app.api.depends.auth import get_authentication_service
from app.models.tokenModel import Token


class FakeAuthenticationService:
    def __init__(self, sample_user):
        self.sample_user = sample_user
        self.refresh_inputs: list[str] = []
        self.user_token_inputs: list[tuple[str, str]] = []

    async def loginUser(self, login_request):
        self.login_request = login_request
        return (
            Token(accessToken="access-token", tokenType="ACCESS_TOKEN"),
            Token(accessToken="refresh-token", tokenType="REFRESH_TOKEN"),
        )

    async def registerUser(self, register_request):
        self.register_request = register_request
        return (
            Token(accessToken="access-token", tokenType="ACCESS_TOKEN"),
            Token(accessToken="refresh-token", tokenType="REFRESH_TOKEN"),
        )

    def generateAccessTokenFromRefreshToken(self, refresh_token: str) -> Token:
        self.refresh_inputs.append(refresh_token)
        return Token(
            accessToken=f"new-access-for-{refresh_token}",
            tokenType="ACCESS_TOKEN",
        )

    async def getUserFromAccessToken(self, access_token: str, refresh_token: str):
        self.user_token_inputs.append((access_token, refresh_token))
        return self.sample_user


@pytest.fixture
def fakeAuth(sampleUser):
    return FakeAuthenticationService(sampleUser)


@pytest.fixture
def client(fakeAuth):
    from main import app

    app.dependency_overrides[get_authentication_service] = lambda: fakeAuth
    test_client = TestClient(app)
    try:
        yield test_client
    finally:
        app.dependency_overrides.clear()
        test_client.close()


@pytest.mark.parametrize(
    ("endpoint", "payload", "expected_message"),
    [
        (
            "/userservices/v1/login",
            {"email": "person@example.com", "password": "StrongPass1!"},
            "Login successful",
        ),
        (
            "/userservices/v1/register",
            {
                "email": "person@example.com",
                "password": "StrongPass1!",
                "dateOfBirth": "2000-01-01T00:00:00Z",
                "firstName": "Person",
                "lastName": "Example",
                "phoneNumber": "+1 555 123 4567",
            },
            "Register successful",
        ),
    ],
)
def test_login_and_register_set_secure_http_only_token_cookies(
    client,
    endpoint,
    payload,
    expected_message,
):
    response = client.post(endpoint, json=payload)

    assert response.status_code == 200
    assert response.json() == {"message": expected_message, "status": "success"}
    assert response.cookies.get("access_token") == "access-token"
    assert response.cookies.get("refresh_token") == "refresh-token"

    set_cookie_header = response.headers["set-cookie"]
    assert "access_token=access-token" in set_cookie_header
    assert "refresh_token=refresh-token" in set_cookie_header
    assert "HttpOnly" in set_cookie_header
    assert "Secure" in set_cookie_header


def test_refresh_prefers_cookie_token_over_body_token(client, fakeAuth):
    client.cookies.set("refresh_token", "cookie-token")

    response = client.post(
        "/userservices/v1/refresh",
        json={"refresh_token": "body-token"},
    )

    assert response.status_code == 200
    assert response.json() == {
        "accessToken": "new-access-for-cookie-token",
        "tokenType": "ACCESS_TOKEN",
    }
    assert fakeAuth.refresh_inputs == ["cookie-token"]


def test_refresh_rejects_missing_refresh_token(client):
    response = client.post("/userservices/v1/refresh")

    assert response.status_code == 401
    assert response.json() == {
        "code": "token_error",
        "message": "No Refresh Token provided",
    }


def test_get_user_from_token_requires_both_cookies(client):
    client.cookies.set("access_token", "access-token")

    response = client.get("/userservices/v1/getUserFromToken")

    assert response.status_code == 401
    assert response.json() == {
        "code": "login_error",
        "message": "Unauthorized Access: No Refresh Token provided",
    }


def test_get_user_from_token_passes_access_and_refresh_cookies(
    client,
    fakeAuth,
    sampleUser,
):
    client.cookies.set("access_token", "access-cookie")
    client.cookies.set("refresh_token", "refresh-cookie")

    response = client.get("/userservices/v1/getUserFromToken")

    assert response.status_code == 200
    assert response.json()["sub"] == sampleUser.sub
    assert response.json()["email"] == sampleUser.email
    assert fakeAuth.user_token_inputs == [("access-cookie", "refresh-cookie")]
