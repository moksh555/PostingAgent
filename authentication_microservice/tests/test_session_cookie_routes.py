import pytest

from app.api.depends.auth import get_authentication_service
from app.models.tokenModel import Token
from main import app


class IssuingAuth:
    async def loginUser(self, request):
        return self._tokens()

    async def registerUser(self, request):
        return self._tokens()

    def _tokens(self) -> tuple[Token, Token]:
        return (
            Token(accessToken="access-token-value", tokenType="ACCESS_TOKEN"),
            Token(accessToken="refresh-token-value", tokenType="REFRESH_TOKEN"),
        )


def _set_cookie_header(response, cookie_name: str) -> str:
    return next(
        header
        for header in response.headers.get_list("set-cookie")
        if header.startswith(f"{cookie_name}=")
    )


@pytest.mark.parametrize(
    ("path", "payload", "message"),
    [
        (
            "/userservices/v1/login",
            {"email": "user@example.com", "password": "StrongPass1!"},
            "Login successful",
        ),
        (
            "/userservices/v1/register",
            {
                "email": "user@example.com",
                "password": "StrongPass1!",
                "dateOfBirth": "1990-01-01T00:00:00Z",
                "firstName": "Test",
                "lastName": "User",
                "phoneNumber": "+15555550123",
            },
            "Register successful",
        ),
    ],
)
def test_auth_success_routes_issue_secure_http_only_session_cookies(
    client,
    path,
    payload,
    message,
):
    app.dependency_overrides[get_authentication_service] = lambda: IssuingAuth()

    response = client.post(path, json=payload)

    assert response.status_code == 200
    assert response.json() == {"message": message, "status": "success"}

    access_cookie = _set_cookie_header(response, "access_token")
    refresh_cookie = _set_cookie_header(response, "refresh_token")

    assert access_cookie.startswith("access_token=access-token-value;")
    assert "Max-Age=1800" in access_cookie
    assert "HttpOnly" in access_cookie
    assert "Secure" in access_cookie

    assert refresh_cookie.startswith("refresh_token=refresh-token-value;")
    assert "Max-Age=432000" in refresh_cookie
    assert "HttpOnly" in refresh_cookie
    assert "Secure" in refresh_cookie
