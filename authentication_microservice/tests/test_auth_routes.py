from app.models.tokenModel import Token


class FakeAuthenticationService:
    def __init__(self, user_factory):
        self._user_factory = user_factory
        self.login_requests = []
        self.register_requests = []
        self.refresh_tokens = []
        self.access_token_pairs = []

    async def loginUser(self, request):
        self.login_requests.append(request)
        return (
            Token(accessToken="access-token", tokenType="ACCESS_TOKEN"),
            Token(accessToken="refresh-token", tokenType="REFRESH_TOKEN"),
        )

    async def registerUser(self, request):
        self.register_requests.append(request)
        return (
            Token(accessToken="registered-access", tokenType="ACCESS_TOKEN"),
            Token(accessToken="registered-refresh", tokenType="REFRESH_TOKEN"),
        )

    def generateAccessTokenFromRefreshToken(self, refresh_token: str):
        self.refresh_tokens.append(refresh_token)
        return Token(accessToken="new-access-token", tokenType="ACCESS_TOKEN")

    async def getUserFromAccessToken(self, access_token: str, refresh_token: str):
        self.access_token_pairs.append((access_token, refresh_token))
        return self._user_factory(sub="user-123", email="user@example.com")


def _cookie_headers(response):
    return response.headers.get_list("set-cookie")


def test_login_sets_secure_http_only_access_and_refresh_cookies(
    client_factory,
    user_model_factory,
):
    fake_auth = FakeAuthenticationService(user_model_factory)
    client = client_factory(fake_auth)

    response = client.post(
        "/userservices/v1/login",
        json={"email": "User@Example.COM", "password": "StrongPass1!"},
    )

    assert response.status_code == 200
    assert response.json() == {
        "message": "Login successful",
        "status": "success",
    }
    cookies = _cookie_headers(response)
    assert any(
        "refresh_token=refresh-token" in cookie
        and "HttpOnly" in cookie
        and "Secure" in cookie
        for cookie in cookies
    )
    assert any(
        "access_token=access-token" in cookie
        and "HttpOnly" in cookie
        and "Secure" in cookie
        for cookie in cookies
    )
    assert fake_auth.login_requests[0].email == "User@Example.COM"


def test_register_sets_secure_http_only_access_and_refresh_cookies(
    client_factory,
    user_model_factory,
    valid_register_payload,
):
    fake_auth = FakeAuthenticationService(user_model_factory)
    client = client_factory(fake_auth)

    response = client.post(
        "/userservices/v1/register",
        json=valid_register_payload().model_dump(mode="json"),
    )

    assert response.status_code == 200
    assert response.json() == {
        "message": "Register successful",
        "status": "success",
    }
    cookies = _cookie_headers(response)
    assert any(
        "refresh_token=registered-refresh" in cookie
        and "HttpOnly" in cookie
        and "Secure" in cookie
        for cookie in cookies
    )
    assert any(
        "access_token=registered-access" in cookie
        and "HttpOnly" in cookie
        and "Secure" in cookie
        for cookie in cookies
    )
    assert fake_auth.register_requests[0].email == " User@Example.COM "


def test_refresh_prefers_http_only_cookie_over_body(
    client_factory,
    user_model_factory,
):
    fake_auth = FakeAuthenticationService(user_model_factory)
    client = client_factory(fake_auth)
    client.cookies.set("refresh_token", "cookie-refresh")

    response = client.post(
        "/userservices/v1/refresh",
        json={"refresh_token": "body-refresh"},
    )

    assert response.status_code == 200
    assert response.json() == {
        "accessToken": "new-access-token",
        "tokenType": "ACCESS_TOKEN",
    }
    assert fake_auth.refresh_tokens == ["cookie-refresh"]


def test_refresh_without_cookie_or_body_returns_credential_error(
    client_factory,
    user_model_factory,
):
    fake_auth = FakeAuthenticationService(user_model_factory)
    client = client_factory(fake_auth)

    response = client.post("/userservices/v1/refresh")

    assert response.status_code == 401
    assert response.json() == {
        "code": "token_error",
        "message": "No Refresh Token provided",
    }
    assert fake_auth.refresh_tokens == []


def test_get_user_from_token_requires_both_cookies(
    client_factory,
    user_model_factory,
):
    fake_auth = FakeAuthenticationService(user_model_factory)
    client_missing_access = client_factory(fake_auth)
    client_missing_access.cookies.set("refresh_token", "refresh-token")
    client_missing_refresh = client_factory(fake_auth)
    client_missing_refresh.cookies.set("access_token", "access-token")

    missing_access = client_missing_access.get(
        "/userservices/v1/getUserFromToken",
    )
    missing_refresh = client_missing_refresh.get(
        "/userservices/v1/getUserFromToken",
    )

    assert missing_access.status_code == 401
    assert missing_access.json() == {
        "code": "login_error",
        "message": "Unauthorized Access: No Access Token provided",
    }
    assert missing_refresh.status_code == 401
    assert missing_refresh.json() == {
        "code": "login_error",
        "message": "Unauthorized Access: No Refresh Token provided",
    }
    assert fake_auth.access_token_pairs == []


def test_get_user_from_token_forwards_cookie_pair_to_auth_service(
    client_factory,
    user_model_factory,
):
    fake_auth = FakeAuthenticationService(user_model_factory)
    client = client_factory(fake_auth)
    client.cookies.set("access_token", "access-token")
    client.cookies.set("refresh_token", "refresh-token")

    response = client.get(
        "/userservices/v1/getUserFromToken",
    )

    assert response.status_code == 200
    assert response.json()["sub"] == "user-123"
    assert response.json()["email"] == "user@example.com"
    assert fake_auth.access_token_pairs == [("access-token", "refresh-token")]
