import asyncio
from datetime import UTC, datetime

import pytest
from fastapi import Response

from app.api.version1.getUserFromToken import getUserFromToken
from app.api.version1.login import login
from app.api.version1.refresh import refresh
from app.api.version1.register import register
from app.errorsHandler.loginError import NotAuthorized
from app.errorsHandler.tokenError import CredentialException
from app.models.loginModel import LoginRequest
from app.models.registerModel import RegisterRequest
from app.models.tokenModel import RefreshRequest, Token
from app.models.userModel import UserModel


def cookie_values(response: Response) -> list[str]:
    return [
        value.decode("latin-1")
        for name, value in response.raw_headers
        if name.decode("latin-1").lower() == "set-cookie"
    ]


def register_payload() -> RegisterRequest:
    return RegisterRequest(
        email="user@example.com",
        password="ValidPass1!",
        dateOfBirth=datetime(1990, 1, 1, tzinfo=UTC),
        firstName="Ada",
        lastName="Lovelace",
        phoneNumber="+1 555 123 4567",
    )


def user_model() -> UserModel:
    return UserModel(
        email="user@example.com",
        sub="user-123",
        userFirstName="Ada",
        userLastName="Lovelace",
        phoneNumber="+1 555 123 4567",
        dateOfBirth=datetime(1990, 1, 1, tzinfo=UTC),
        createdAt=datetime(2026, 1, 1, tzinfo=UTC),
        isActive=True,
        subscriptionType="free",
    )


class FakeAuth:
    def __init__(self):
        self.refresh_inputs = []
        self.access_inputs = []

    async def loginUser(self, request):
        return (
            Token(accessToken="access-token", tokenType="ACCESS_TOKEN"),
            Token(accessToken="refresh-token", tokenType="REFRESH_TOKEN"),
        )

    async def registerUser(self, request):
        return (
            Token(accessToken="registered-access-token", tokenType="ACCESS_TOKEN"),
            Token(accessToken="registered-refresh-token", tokenType="REFRESH_TOKEN"),
        )

    def generateAccessTokenFromRefreshToken(self, refresh_token):
        self.refresh_inputs.append(refresh_token)
        return Token(accessToken=f"access-from-{refresh_token}", tokenType="ACCESS_TOKEN")

    async def getUserFromAccessToken(self, access_token, refresh_token):
        self.access_inputs.append((access_token, refresh_token))
        return user_model()


class TestLoginAndRegisterRoutes:
    @pytest.mark.parametrize(
        ("handler", "request_obj", "expected_message", "access_token", "refresh_token"),
        [
            (
                login,
                LoginRequest(email="user@example.com", password="ValidPass1!"),
                "Login successful",
                "access-token",
                "refresh-token",
            ),
            (
                register,
                register_payload(),
                "Register successful",
                "registered-access-token",
                "registered-refresh-token",
            ),
        ],
    )
    def test_success_sets_secure_http_only_access_and_refresh_cookies(
        self,
        handler,
        request_obj,
        expected_message,
        access_token,
        refresh_token,
    ):
        response = Response()

        body = asyncio.run(handler(request_obj, response, auth=FakeAuth()))

        assert body.message == expected_message
        assert body.status == "success"
        cookies = cookie_values(response)
        assert any(
            f"refresh_token={refresh_token}" in cookie
            and "HttpOnly" in cookie
            and "Secure" in cookie
            and "Max-Age=432000" in cookie
            for cookie in cookies
        )
        assert any(
            f"access_token={access_token}" in cookie
            and "HttpOnly" in cookie
            and "Secure" in cookie
            and "Max-Age=1800" in cookie
            for cookie in cookies
        )


class TestRefreshRoute:
    def test_cookie_refresh_token_takes_precedence_over_body_token(self):
        auth = FakeAuth()

        token = asyncio.run(
            refresh(
                auth=auth,
                refresh_token_cookie="cookie-token",
                body=RefreshRequest(refresh_token="body-token"),
            ),
        )

        assert token.accessToken == "access-from-cookie-token"
        assert auth.refresh_inputs == ["cookie-token"]

    def test_body_refresh_token_used_when_cookie_missing(self):
        auth = FakeAuth()

        token = asyncio.run(
            refresh(
                auth=auth,
                refresh_token_cookie=None,
                body=RefreshRequest(refresh_token="body-token"),
            ),
        )

        assert token.accessToken == "access-from-body-token"
        assert auth.refresh_inputs == ["body-token"]

    def test_missing_refresh_token_rejected(self):
        with pytest.raises(CredentialException):
            asyncio.run(refresh(auth=FakeAuth(), refresh_token_cookie=None, body=None))


class TestGetUserFromTokenRoute:
    def test_requires_access_cookie(self):
        with pytest.raises(NotAuthorized) as exc_info:
            asyncio.run(
                getUserFromToken(access_token=None, refresh_token="refresh-token", auth=FakeAuth()),
            )

        assert exc_info.value.message == "Unauthorized Access: No Access Token provided"

    def test_requires_refresh_cookie(self):
        with pytest.raises(NotAuthorized) as exc_info:
            asyncio.run(
                getUserFromToken(access_token="access-token", refresh_token=None, auth=FakeAuth()),
            )

        assert exc_info.value.message == "Unauthorized Access: No Refresh Token provided"

    def test_passes_cookie_tokens_to_auth_service(self):
        auth = FakeAuth()

        user = asyncio.run(
            getUserFromToken(
                access_token="access-token",
                refresh_token="refresh-token",
                auth=auth,
            ),
        )

        assert user.sub == "user-123"
        assert auth.access_inputs == [("access-token", "refresh-token")]
