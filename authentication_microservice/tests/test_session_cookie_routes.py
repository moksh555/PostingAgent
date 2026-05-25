import pytest
from unittest.mock import Mock


@pytest.mark.parametrize(
    ("endpoint", "payload", "auth_method", "access_token", "refresh_token", "message"),
    [
        (
            "/userservices/v1/login",
            {"email": "user@example.com", "password": "CorrectHorse1!"},
            "loginUser",
            "login-access-token",
            "login-refresh-token",
            "Login successful",
        ),
        (
            "/userservices/v1/register",
            {
                "email": "user@example.com",
                "password": "CorrectHorse1!",
                "dateOfBirth": "1990-01-01T00:00:00Z",
                "firstName": "Test",
                "lastName": "User",
                "phoneNumber": "+15555550123",
            },
            "registerUser",
            "register-access-token",
            "register-refresh-token",
            "Register successful",
        ),
    ],
)
def test_auth_routes_set_expected_session_cookies(
    client,
    fake_auth: Mock,
    endpoint: str,
    payload: dict[str, str],
    auth_method: str,
    access_token: str,
    refresh_token: str,
    message: str,
) -> None:
    response = client.post(endpoint, json=payload)

    assert response.status_code == 200
    assert response.json() == {"message": message, "status": "success"}
    getattr(fake_auth, auth_method).assert_awaited_once()

    set_cookie_headers = response.headers.get_list("set-cookie")
    assert _cookie_header(set_cookie_headers, "access_token").startswith(
        f"access_token={access_token};",
    )
    assert _cookie_header(set_cookie_headers, "refresh_token").startswith(
        f"refresh_token={refresh_token};",
    )
    assert "HttpOnly" in _cookie_header(set_cookie_headers, "access_token")
    assert "Secure" in _cookie_header(set_cookie_headers, "access_token")
    assert "HttpOnly" in _cookie_header(set_cookie_headers, "refresh_token")
    assert "Secure" in _cookie_header(set_cookie_headers, "refresh_token")


def _cookie_header(headers: list[str], cookie_name: str) -> str:
    matches = [header for header in headers if header.startswith(f"{cookie_name}=")]
    assert len(matches) == 1
    return matches[0]
