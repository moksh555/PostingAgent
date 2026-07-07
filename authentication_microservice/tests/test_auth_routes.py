from datetime import UTC, datetime
from unittest.mock import Mock

from app.models.tokenModel import Token


def _cookie_headers(response):
    return response.headers.get_list("set-cookie")


def _has_cookie(headers, name, value, max_age):
    return any(
        f"{name}={value}" in header
        and "HttpOnly" in header
        and "Secure" in header
        and f"Max-Age={max_age}" in header
        for header in headers
    )


class TestLoginCookies:
    def test_login_sets_secure_http_only_access_and_refresh_cookies(
        self,
        client,
        auth_route_service,
    ):
        auth_route_service.loginUser.return_value = (
            Token(accessToken="access.jwt", tokenType="ACCESS_TOKEN"),
            Token(accessToken="refresh.jwt", tokenType="REFRESH_TOKEN"),
        )

        response = client.post(
            "/userservices/v1/login",
            json={"email": "user@example.com", "password": "CorrectHorse1!"},
        )

        assert response.status_code == 200
        assert response.json() == {"message": "Login successful", "status": "success"}
        headers = _cookie_headers(response)
        assert _has_cookie(headers, "access_token", "access.jwt", 1800)
        assert _has_cookie(headers, "refresh_token", "refresh.jwt", 3600 * 24 * 5)
        auth_route_service.loginUser.assert_awaited_once()


class TestRegisterCookies:
    def test_register_sets_secure_http_only_access_and_refresh_cookies(
        self,
        client,
        auth_route_service,
    ):
        auth_route_service.registerUser.return_value = (
            Token(accessToken="new-access.jwt", tokenType="ACCESS_TOKEN"),
            Token(accessToken="new-refresh.jwt", tokenType="REFRESH_TOKEN"),
        )

        response = client.post(
            "/userservices/v1/register",
            json={
                "email": "new-user@example.com",
                "password": "CorrectHorse1!",
                "dateOfBirth": datetime(1995, 1, 1, tzinfo=UTC).isoformat(),
                "firstName": "New",
                "lastName": "User",
                "phoneNumber": "+15555550123",
            },
        )

        assert response.status_code == 200
        assert response.json() == {"message": "Register successful", "status": "success"}
        headers = _cookie_headers(response)
        assert _has_cookie(headers, "access_token", "new-access.jwt", 1800)
        assert _has_cookie(headers, "refresh_token", "new-refresh.jwt", 3600 * 24 * 5)
        auth_route_service.registerUser.assert_awaited_once()


class TestRefreshRoute:
    def test_refresh_prefers_refresh_cookie_over_json_body(
        self,
        client,
        auth_route_service,
    ):
        auth_route_service.generateAccessTokenFromRefreshToken = Mock(
            return_value=Token(accessToken="new-access.jwt", tokenType="ACCESS_TOKEN"),
        )

        response = client.post(
            "/userservices/v1/refresh",
            headers={"Cookie": "refresh_token=cookie-refresh.jwt"},
            json={"refresh_token": "body-refresh.jwt"},
        )

        assert response.status_code == 200
        assert response.json() == {
            "accessToken": "new-access.jwt",
            "tokenType": "ACCESS_TOKEN",
        }
        auth_route_service.generateAccessTokenFromRefreshToken.assert_called_once_with(
            "cookie-refresh.jwt",
        )

    def test_refresh_uses_json_body_when_cookie_missing(self, client, auth_route_service):
        auth_route_service.generateAccessTokenFromRefreshToken = Mock(
            return_value=Token(accessToken="body-access.jwt", tokenType="ACCESS_TOKEN"),
        )

        response = client.post(
            "/userservices/v1/refresh",
            json={"refresh_token": "body-refresh.jwt"},
        )

        assert response.status_code == 200
        assert response.json() == {
            "accessToken": "body-access.jwt",
            "tokenType": "ACCESS_TOKEN",
        }
        auth_route_service.generateAccessTokenFromRefreshToken.assert_called_once_with(
            "body-refresh.jwt",
        )

    def test_refresh_without_cookie_or_body_returns_token_error(self, client):
        response = client.post("/userservices/v1/refresh")

        assert response.status_code == 401
        assert response.json() == {
            "code": "token_error",
            "message": "No Refresh Token provided",
        }


class TestGetUserFromTokenRoute:
    def test_requires_access_cookie(self, client):
        response = client.get(
            "/userservices/v1/getUserFromToken",
            headers={"Cookie": "refresh_token=refresh.jwt"},
        )

        assert response.status_code == 401
        assert response.json() == {
            "code": "login_error",
            "message": "Unauthorized Access: No Access Token provided",
        }

    def test_requires_refresh_cookie(self, client):
        response = client.get(
            "/userservices/v1/getUserFromToken",
            headers={"Cookie": "access_token=access.jwt"},
        )

        assert response.status_code == 401
        assert response.json() == {
            "code": "login_error",
            "message": "Unauthorized Access: No Refresh Token provided",
        }

    def test_forwards_access_and_refresh_cookie_pair_to_auth_service(
        self,
        client,
        auth_route_service,
    ):
        response = client.get(
            "/userservices/v1/getUserFromToken",
            headers={"Cookie": "access_token=access.jwt; refresh_token=refresh.jwt"},
        )

        assert response.status_code == 200
        assert response.json()["sub"] == "user-1"
        auth_route_service.getUserFromAccessToken.assert_awaited_once_with(
            "access.jwt",
            "refresh.jwt",
        )
