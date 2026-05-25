from unittest.mock import Mock


class TestRefreshRoute:
    def test_refresh_uses_cookie_before_body(self, client, fake_auth: Mock) -> None:
        response = client.post(
            "/userservices/v1/refresh",
            cookies={"refresh_token": "cookie-refresh-token"},
            json={"refresh_token": "body-refresh-token"},
        )

        assert response.status_code == 200
        assert response.json() == {
            "accessToken": "new-access-token",
            "tokenType": "ACCESS_TOKEN",
        }
        fake_auth.generateAccessTokenFromRefreshToken.assert_called_once_with(
            "cookie-refresh-token",
        )

    def test_refresh_accepts_json_body_when_cookie_missing(
        self,
        client,
        fake_auth: Mock,
    ) -> None:
        response = client.post(
            "/userservices/v1/refresh",
            json={"refresh_token": "body-refresh-token"},
        )

        assert response.status_code == 200
        fake_auth.generateAccessTokenFromRefreshToken.assert_called_once_with(
            "body-refresh-token",
        )

    def test_refresh_rejects_missing_token(self, client, fake_auth: Mock) -> None:
        response = client.post("/userservices/v1/refresh")

        assert response.status_code == 401
        assert response.json() == {
            "code": "token_error",
            "message": "No Refresh Token provided",
        }
        fake_auth.generateAccessTokenFromRefreshToken.assert_not_called()
