from app.models.tokenModel import Token


def _install_auth_override(fake_auth):
    from app.api.depends.auth import get_authentication_service
    from main import app

    app.dependency_overrides[get_authentication_service] = lambda: fake_auth


def _cookie_header(response, cookie_name: str) -> str:
    for header in response.headers.get_list("set-cookie"):
        if header.startswith(f"{cookie_name}="):
            return header
    raise AssertionError(f"Missing {cookie_name} Set-Cookie header")


class TokenIssuingAuth:
    def __init__(self):
        self.requests = []

    async def loginUser(self, request):
        self.requests.append(request)
        return (
            Token(accessToken="access-token-from-login", tokenType="ACCESS_TOKEN"),
            Token(accessToken="refresh-token-from-login", tokenType="REFRESH_TOKEN"),
        )

    async def registerUser(self, request):
        self.requests.append(request)
        return (
            Token(accessToken="access-token-from-register", tokenType="ACCESS_TOKEN"),
            Token(accessToken="refresh-token-from-register", tokenType="REFRESH_TOKEN"),
        )


def test_login_sets_http_only_secure_access_and_refresh_cookies(app_client):
    fake_auth = TokenIssuingAuth()
    _install_auth_override(fake_auth)

    response = app_client.post(
        "/userservices/v1/login",
        json={"email": "USER@example.com", "password": "CorrectHorse1!"},
    )

    assert response.status_code == 200
    assert response.json() == {"message": "Login successful", "status": "success"}
    access_cookie = _cookie_header(response, "access_token")
    refresh_cookie = _cookie_header(response, "refresh_token")
    assert "access_token=access-token-from-login" in access_cookie
    assert "Max-Age=1800" in access_cookie
    assert "HttpOnly" in access_cookie
    assert "Secure" in access_cookie
    assert "refresh_token=refresh-token-from-login" in refresh_cookie
    assert "Max-Age=432000" in refresh_cookie
    assert "HttpOnly" in refresh_cookie
    assert "Secure" in refresh_cookie


def test_register_sets_http_only_secure_access_and_refresh_cookies(app_client):
    fake_auth = TokenIssuingAuth()
    _install_auth_override(fake_auth)

    response = app_client.post(
        "/userservices/v1/register",
        json={
            "email": "user@example.com",
            "password": "CorrectHorse1!",
            "dateOfBirth": "1990-01-01T00:00:00Z",
            "firstName": "Test",
            "lastName": "User",
            "phoneNumber": "+15551234567",
        },
    )

    assert response.status_code == 200
    assert response.json() == {"message": "Register successful", "status": "success"}
    access_cookie = _cookie_header(response, "access_token")
    refresh_cookie = _cookie_header(response, "refresh_token")
    assert "access_token=access-token-from-register" in access_cookie
    assert "Max-Age=1800" in access_cookie
    assert "HttpOnly" in access_cookie
    assert "Secure" in access_cookie
    assert "refresh_token=refresh-token-from-register" in refresh_cookie
    assert "Max-Age=432000" in refresh_cookie
    assert "HttpOnly" in refresh_cookie
    assert "Secure" in refresh_cookie


def test_refresh_prefers_refresh_cookie_over_body_token(app_client):
    class RefreshAuth:
        def __init__(self):
            self.seen_tokens = []

        def generateAccessTokenFromRefreshToken(self, refresh_token: str):
            self.seen_tokens.append(refresh_token)
            return Token(accessToken="new-access-token", tokenType="ACCESS_TOKEN")

    fake_auth = RefreshAuth()
    _install_auth_override(fake_auth)

    response = app_client.post(
        "/userservices/v1/refresh",
        cookies={"refresh_token": "cookie-refresh-token"},
        json={"refresh_token": "body-refresh-token"},
    )

    assert response.status_code == 200
    assert response.json() == {
        "accessToken": "new-access-token",
        "tokenType": "ACCESS_TOKEN",
    }
    assert fake_auth.seen_tokens == ["cookie-refresh-token"]


def test_refresh_accepts_body_token_when_cookie_is_missing(app_client):
    class RefreshAuth:
        def __init__(self):
            self.seen_tokens = []

        def generateAccessTokenFromRefreshToken(self, refresh_token: str):
            self.seen_tokens.append(refresh_token)
            return Token(accessToken="new-access-token", tokenType="ACCESS_TOKEN")

    fake_auth = RefreshAuth()
    _install_auth_override(fake_auth)

    response = app_client.post(
        "/userservices/v1/refresh",
        json={"refresh_token": "body-refresh-token"},
    )

    assert response.status_code == 200
    assert response.json() == {
        "accessToken": "new-access-token",
        "tokenType": "ACCESS_TOKEN",
    }
    assert fake_auth.seen_tokens == ["body-refresh-token"]


def test_get_user_from_token_requires_access_cookie(app_client):
    response = app_client.get(
        "/userservices/v1/getUserFromToken",
        cookies={"refresh_token": "refresh-token"},
    )

    assert response.status_code == 401
    assert response.json() == {
        "code": "login_error",
        "message": "Unauthorized Access: No Access Token provided",
    }


def test_get_user_from_token_loads_user_from_access_and_refresh_cookies(
    app_client,
    user_model,
):
    class SessionAuth:
        def __init__(self):
            self.seen_tokens = []

        async def getUserFromAccessToken(self, access_token: str, refresh_token: str):
            self.seen_tokens.append((access_token, refresh_token))
            return user_model

    fake_auth = SessionAuth()
    _install_auth_override(fake_auth)

    response = app_client.get(
        "/userservices/v1/getUserFromToken",
        cookies={
            "access_token": "access-cookie-token",
            "refresh_token": "refresh-cookie-token",
        },
    )

    assert response.status_code == 200
    assert response.json()["sub"] == "user-123"
    assert response.json()["email"] == "user@example.com"
    assert fake_auth.seen_tokens == [
        ("access-cookie-token", "refresh-cookie-token"),
    ]
