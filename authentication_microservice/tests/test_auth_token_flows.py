import asyncio
from datetime import UTC, datetime, timedelta

import jwt  # type: ignore
import pytest

from app.api.version1.getUserFromToken import getUserFromToken
from app.api.version1.refresh import refresh
from app.errorsHandler.loginError import NotAuthorized
from app.errorsHandler.tokenError import CredentialException
from app.models.tokenModel import RefreshRequest, Token, TokenModel
from app.models.userModel import UserModel
from app.services import authenticationService as auth_module
from app.services.authenticationService import AuthenticationService
from configurations.config import config


@pytest.fixture
def auth_service() -> AuthenticationService:
    return AuthenticationService(db=object())


@pytest.fixture
def token_data() -> TokenModel:
    return TokenModel(sub="user-123", email="person@example.com")


@pytest.fixture
def user() -> UserModel:
    return UserModel(
        email="person@example.com",
        sub="user-123",
        userFirstName="Test",
        userLastName="User",
        phoneNumber="+15555550123",
        dateOfBirth=datetime(2000, 1, 1, tzinfo=UTC),
        createdAt=datetime(2026, 5, 1, tzinfo=UTC),
        isActive=True,
        subscriptionType="free",
    )


def test_refresh_token_mints_access_token_with_expected_claims(
    auth_service: AuthenticationService,
    token_data: TokenModel,
) -> None:
    refresh_token = auth_service._encodeRefreshToken(token_data, timedelta(minutes=5))

    access_token = auth_service.generateAccessTokenFromRefreshToken(refresh_token)

    payload = jwt.decode(
        access_token.accessToken,
        config.AUTHENTICATION_SECRET_KEY,
        algorithms=[config.AUTHENTICATION_ALGORITHM],
    )
    assert access_token.tokenType == "ACCESS_TOKEN"
    assert payload["sub"] == token_data.sub
    assert payload["email"] == token_data.email


def test_access_token_cannot_be_used_as_refresh_token(
    auth_service: AuthenticationService,
    token_data: TokenModel,
) -> None:
    access_token = auth_service._encodeAccessToken(token_data, timedelta(minutes=5))

    with pytest.raises(CredentialException):
        auth_service.generateAccessTokenFromRefreshToken(access_token)


def test_expired_refresh_token_is_not_authorized(
    auth_service: AuthenticationService,
    token_data: TokenModel,
) -> None:
    expired_refresh = auth_service._encodeRefreshToken(
        token_data,
        timedelta(seconds=-1),
    )

    with pytest.raises(NotAuthorized, match="Refresh token expired"):
        auth_service.generateAccessTokenFromRefreshToken(expired_refresh)


def test_expired_access_token_refreshes_and_loads_user(
    auth_service: AuthenticationService,
    token_data: TokenModel,
    user: UserModel,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    requested_user_ids: list[str] = []

    class FakeUserService:
        def __init__(self, db: object) -> None:
            self.db = db

        async def getUserFromUserId(self, user_id: str) -> UserModel:
            requested_user_ids.append(user_id)
            return user

    monkeypatch.setattr(auth_module, "UserService", FakeUserService)
    expired_access = auth_service._encodeAccessToken(token_data, timedelta(seconds=-1))
    valid_refresh = auth_service._encodeRefreshToken(token_data, timedelta(minutes=5))

    result = asyncio.run(
        auth_service.getUserFromAccessToken(expired_access, valid_refresh),
    )

    assert result == user
    assert requested_user_ids == [token_data.sub]


def test_invalid_access_token_does_not_attempt_refresh(
    auth_service: AuthenticationService,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    attempted_refresh = False

    def fail_if_called(refresh_token: str) -> Token:
        nonlocal attempted_refresh
        attempted_refresh = True
        raise AssertionError(f"Unexpected refresh attempt for {refresh_token}")

    monkeypatch.setattr(
        auth_service,
        "generateAccessTokenFromRefreshToken",
        fail_if_called,
    )

    with pytest.raises(CredentialException):
        asyncio.run(auth_service.getUserFromAccessToken("not-a-jwt", "refresh-token"))

    assert attempted_refresh is False


def test_refresh_endpoint_prefers_cookie_token_over_body() -> None:
    class StubAuth:
        def __init__(self) -> None:
            self.refresh_tokens: list[str] = []

        def generateAccessTokenFromRefreshToken(self, refresh_token: str) -> Token:
            self.refresh_tokens.append(refresh_token)
            return Token(
                accessToken=f"access-for-{refresh_token}",
                tokenType="ACCESS_TOKEN",
            )

    auth = StubAuth()

    result = asyncio.run(
        refresh(
            auth=auth,
            refresh_token_cookie="cookie-token",
            body=RefreshRequest(refresh_token="body-token"),
        ),
    )

    assert result.accessToken == "access-for-cookie-token"
    assert auth.refresh_tokens == ["cookie-token"]


def test_refresh_endpoint_uses_body_when_cookie_absent() -> None:
    class StubAuth:
        def generateAccessTokenFromRefreshToken(self, refresh_token: str) -> Token:
            return Token(
                accessToken=f"access-for-{refresh_token}",
                tokenType="ACCESS_TOKEN",
            )

    result = asyncio.run(
        refresh(
            auth=StubAuth(),
            refresh_token_cookie=None,
            body=RefreshRequest(refresh_token="body-token"),
        ),
    )

    assert result.accessToken == "access-for-body-token"


def test_refresh_endpoint_rejects_missing_token() -> None:
    with pytest.raises(CredentialException, match="No Refresh Token provided"):
        asyncio.run(refresh(auth=object(), refresh_token_cookie=None, body=None))


def test_get_user_from_token_requires_access_and_refresh_cookies(
    user: UserModel,
) -> None:
    class StubAuth:
        def __init__(self) -> None:
            self.calls: list[tuple[str, str]] = []

        async def getUserFromAccessToken(
            self,
            access_token: str,
            refresh_token: str,
        ) -> UserModel:
            self.calls.append((access_token, refresh_token))
            return user

    auth = StubAuth()

    result = asyncio.run(
        getUserFromToken(
            access_token="access-cookie",
            refresh_token="refresh-cookie",
            auth=auth,
        ),
    )

    assert result == user
    assert auth.calls == [("access-cookie", "refresh-cookie")]


@pytest.mark.parametrize(
    ("access_token", "refresh_token", "message"),
    [
        (None, "refresh-cookie", "No Access Token provided"),
        ("access-cookie", None, "No Refresh Token provided"),
    ],
)
def test_get_user_from_token_rejects_missing_required_cookie(
    access_token: str | None,
    refresh_token: str | None,
    message: str,
) -> None:
    with pytest.raises(NotAuthorized, match=message):
        asyncio.run(
            getUserFromToken(
                access_token=access_token,
                refresh_token=refresh_token,
                auth=object(),
            ),
        )
