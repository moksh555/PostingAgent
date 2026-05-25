from unittest.mock import Mock


class TestGetUserFromTokenRoute:
    def test_missing_access_cookie_is_rejected(self, client, fake_auth: Mock) -> None:
        response = client.get(
            "/userservices/v1/getUserFromToken",
            cookies={"refresh_token": "refresh-token"},
        )

        assert response.status_code == 401
        assert response.json() == {
            "code": "login_error",
            "message": "Unauthorized Access: No Access Token provided",
        }
        fake_auth.getUserFromAccessToken.assert_not_awaited()

    def test_missing_refresh_cookie_is_rejected(self, client, fake_auth: Mock) -> None:
        response = client.get(
            "/userservices/v1/getUserFromToken",
            cookies={"access_token": "access-token"},
        )

        assert response.status_code == 401
        assert response.json() == {
            "code": "login_error",
            "message": "Unauthorized Access: No Refresh Token provided",
        }
        fake_auth.getUserFromAccessToken.assert_not_awaited()

    def test_both_cookies_delegate_to_auth_service(
        self,
        client,
        fake_auth: Mock,
    ) -> None:
        response = client.get(
            "/userservices/v1/getUserFromToken",
            cookies={
                "access_token": "access-token",
                "refresh_token": "refresh-token",
            },
        )

        assert response.status_code == 200
        assert response.json()["sub"] == "user-123"
        fake_auth.getUserFromAccessToken.assert_awaited_once_with(
            "access-token",
            "refresh-token",
        )
