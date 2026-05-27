from app.api.depends.auth import get_authentication_service
from main import app


class RecordingUserLookupAuth:
    def __init__(self, user) -> None:
        self.user = user
        self.lookups: list[tuple[str, str]] = []

    async def getUserFromAccessToken(self, access_token: str, refresh_token: str):
        self.lookups.append((access_token, refresh_token))
        return self.user


def test_get_user_from_token_requires_access_cookie(client, sample_user):
    auth = RecordingUserLookupAuth(sample_user)
    app.dependency_overrides[get_authentication_service] = lambda: auth

    response = client.get(
        "/userservices/v1/getUserFromToken",
        cookies={"refresh_token": "refresh-token"},
    )

    assert response.status_code == 401
    assert response.json() == {
        "code": "login_error",
        "message": "Unauthorized Access: No Access Token provided",
    }
    assert auth.lookups == []


def test_get_user_from_token_requires_refresh_cookie(client, sample_user):
    auth = RecordingUserLookupAuth(sample_user)
    app.dependency_overrides[get_authentication_service] = lambda: auth

    response = client.get(
        "/userservices/v1/getUserFromToken",
        cookies={"access_token": "access-token"},
    )

    assert response.status_code == 401
    assert response.json() == {
        "code": "login_error",
        "message": "Unauthorized Access: No Refresh Token provided",
    }
    assert auth.lookups == []


def test_get_user_from_token_uses_cookie_tokens_for_lookup(client, sample_user):
    auth = RecordingUserLookupAuth(sample_user)
    app.dependency_overrides[get_authentication_service] = lambda: auth

    response = client.get(
        "/userservices/v1/getUserFromToken",
        cookies={
            "access_token": "access-token",
            "refresh_token": "refresh-token",
        },
    )

    assert response.status_code == 200
    assert response.json()["sub"] == "user-123"
    assert response.json()["email"] == "user@example.com"
    assert auth.lookups == [("access-token", "refresh-token")]
